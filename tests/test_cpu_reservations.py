import importlib.util
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/'cpu/cpu-reservations.py'


class Reservations(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('reservations',SOURCE)
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'CPU.md'
        self.path.write_text('# CPU reservations\n\nLogical CPUs: 6\nSystem reserve: 4\n'
            'Project CPU limit: 5\n\n| Project | Count | Reserved | Active | Borrowed |\n'
            '| --- | --- | --- | --- | --- |\n| alpha | 2 | 0,1 | true | - |\n'
            '| beta | 2 | 2,3 | false | - |\n')

    def test_inactive_borrow_resume_and_release(self):
        self.m.change(self.path,'alpha','borrow',{2},False)
        s=self.m.status(self.path)
        self.assertEqual(s['alpha']['usable'],[0,1,2])
        self.m.change(self.path,'beta','active',set(),False)
        s=self.m.status(self.path)
        self.assertEqual(s['beta']['usable'],[3])
        self.assertEqual(s['alpha']['return_at_boundary'],[2])
        self.assertEqual(s['alpha']['usable'],[0,1])
        with self.assertRaises(ValueError):self.m.change(self.path,'alpha','release',{2},False)
        self.m.change(self.path,'alpha','release',{2},True)
        self.assertEqual(self.m.status(self.path)['beta']['usable'],[2,3])

    def test_active_or_reserved_host_cannot_be_borrowed(self):
        with self.assertRaises(ValueError):self.m.change(self.path,'alpha','borrow',{4},False)
        self.m.change(self.path,'beta','active',set(),False)
        with self.assertRaises(ValueError):self.m.change(self.path,'alpha','borrow',{2},False)

    def test_inactive_requires_drain_and_rejects_duplicate_claim(self):
        with self.assertRaises(ValueError):self.m.change(self.path,'alpha','inactive',set(),False)
        self.m.change(self.path,'alpha','borrow',{2},False)
        self.path.write_text(self.path.read_text()+'| gamma | 1 | 5 | true | - |\n')
        with self.assertRaises(ValueError):self.m.change(self.path,'gamma','borrow',{2},False)

    def test_idempotent_flag_updates_do_not_grow_file(self):
        initial=self.path.read_text()
        for _ in range(5):self.m.change(self.path,'alpha','active',set(),False)
        self.assertEqual(initial,self.path.read_text())
        self.m.change(self.path,'alpha','inactive',set(),True)
        self.m.change(self.path,'alpha','active',set(),False)
        self.assertEqual(initial,self.path.read_text())

    def test_concurrent_borrow_has_only_one_winner(self):
        self.path.write_text(self.path.read_text()+'| gamma | 1 | 5 | true | - |\n')
        processes=[subprocess.Popen([sys.executable,str(SOURCE),'--file',str(self.path),
            '--project',name,'--cpus','2','borrow'],stdout=subprocess.PIPE,
            stderr=subprocess.PIPE) for name in ['alpha','gamma']]
        for process in processes:process.communicate(timeout=5)
        self.assertEqual(sorted(p.returncode for p in processes),[0,1])
        self.assertEqual(sum(2 in r['borrowed'] for r in self.m.status(self.path).values()),1)

    def test_host_limit_system_reserve_and_row_count_are_validated(self):
        original=self.path.read_text()
        for invalid in [original.replace('Project CPU limit: 5','Project CPU limit: 3'),
                        original.replace('| alpha | 2 | 0,1','| alpha | 2 | 0,4'),
                        original.replace('| alpha | 2 | 0,1','| alpha | 2 | 0,6'),
                        original.replace('| alpha | 2 |','| alpha | 3 |')]:
            self.path.write_text(invalid)
            with self.assertRaises(ValueError):self.m.status(self.path)

    def test_project_count_and_file_length_have_no_fixed_cap(self):
        self.path.write_text(self.path.read_text()+''.join(
            f'| project-{i} | 0 | - | false | - |\n' for i in range(30)))
        self.assertEqual(len(self.m.status(self.path)),32)

    def test_inactive_flag_does_not_lend_a_pool_with_live_work(self):
        initial=self.path.read_text()
        with patch.object(self.m,'verify_drained',side_effect=ValueError('live owner work')):
            with self.assertRaisesRegex(ValueError,'live owner work'):
                self.m.change(self.path,'alpha','borrow',{2},False)
        self.assertEqual(self.path.read_text(),initial)


if __name__=='__main__':unittest.main()
