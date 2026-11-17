import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


class CPUInstaller(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('install_cpu',ROOT/'scripts/install_cpu.py')
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
        self.temp=tempfile.TemporaryDirectory(prefix='cpu setup ');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.home=self.root/'user home';self.home.mkdir()
        self.table=self.root/'CPU.md';self.table.write_text('Logical CPUs: 8\nSystem reserve: 0,1\nProject CPU limit: 6\n'
            '| Project | Count | Reserved | Active | Borrowed |\n| --- | --- | --- | --- | --- |\n'
            '| alpha | 4 | 2,3,4,5 | true | - |\n| beta | 2 | 6,7 | false | - |\n')
        self.config=self.root/'input.json'
        self.config.write_text(json.dumps({'file':str(self.table),'projects':{
            'alpha':{'roots':[str(self.root/'alpha')],'unit_prefixes':['alpha-']},
            'beta':{'roots':[str(self.root/'beta')],'unit_prefixes':['beta-']}}}))

    def test_preview_writes_nothing_and_lists_concrete_targets(self):
        before=list(self.home.rglob('*'))
        result=self.m.install(self.m.prepare(self.home,self.config,['claude']))
        self.assertFalse(result['applied']);self.assertFalse(result['cpu_table_modified'])
        self.assertTrue(result['targets']);self.assertEqual(list(self.home.rglob('*')),before)

    def test_claude_install_preserves_permissions_and_removal_restores_hooks(self):
        settings=self.home/'.claude/settings.json';settings.parent.mkdir()
        original={'model':'user-selected','permissions':{'deny':['example']},
                  'hooks':{'PostToolUse':[{'hooks':[{'type':'command','command':'unrelated'}]}]}}
        settings.write_text(json.dumps(original));table=self.table.read_text()
        with patch.object(self.m.subprocess,'run',return_value=subprocess.CompletedProcess([],0)):
            plan=self.m.prepare(self.home,self.config,['claude']);self.m.install(plan,apply=True)
            first=settings.read_text()
            self.m.install(self.m.prepare(self.home,self.config,['claude']),apply=True)
            self.assertEqual(settings.read_text(),first)
            data=json.loads(first)
            self.assertEqual(data['model'],original['model']);self.assertEqual(data['permissions'],original['permissions'])
            self.assertEqual(len(data['hooks']['PreToolUse']),1)
            self.assertEqual(data['hooks']['PostToolUse'][0],original['hooks']['PostToolUse'][0])
            launcher=self.home/'.local/bin/cpu-enforce'
            self.assertTrue(launcher.is_file())
            compact=self.home/'.local/bin/cpu-run'
            self.assertTrue(compact.is_file())
            self.assertTrue(json.loads(plan['config'].read_text())['compact_commands'])
            child=subprocess.Popen([str(launcher),'--help'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            out,err=child.communicate(timeout=5)
            self.assertEqual(child.returncode,0,err);self.assertIn('CPU admission',out)
            self.m.install(self.m.prepare(self.home,self.config,['claude'],remove=True),apply=True,remove=True)
            self.assertFalse(compact.exists())
            remaining=json.loads(settings.read_text())
            self.assertEqual(remaining['permissions'],original['permissions'])
            self.assertEqual(remaining['hooks']['PostToolUse'],original['hooks']['PostToolUse'])
            self.assertFalse(remaining['hooks']['PreToolUse'])
        self.assertEqual(self.table.read_text(),table)

    def test_guardian_failure_does_not_enable_shell_hooks(self):
        plan=self.m.prepare(self.home,self.config,['claude'])
        def runner(args,**kwargs):
            if 'enable' in args: raise subprocess.CalledProcessError(1,args)
            return subprocess.CompletedProcess(args,1)
        with patch.object(self.m.subprocess,'run',side_effect=runner):
            with self.assertRaises(subprocess.CalledProcessError):self.m.install(plan,apply=True)
        self.assertFalse((self.home/'.claude/settings.json').exists())

    def test_existing_input_rewriter_is_preserved(self):
        p=self.home/'.claude/settings.json';p.parent.mkdir()
        text=json.dumps({'hooks':{'PreToolUse':[{'matcher':'Bash','hooks':[{'command':'existing'}]}]}})
        p.write_text(text)
        with self.assertRaisesRegex(ValueError,'concurrent rewrites'):self.m.prepare(self.home,self.config,['claude'])
        self.assertEqual(p.read_text(),text)

    def test_foreign_guardian_is_never_overwritten(self):
        p=self.home/'.config/systemd/user/cpu-reservation-guardian.service';p.parent.mkdir(parents=True)
        p.write_text('keep existing service')
        with self.assertRaisesRegex(ValueError,'unmanaged'):self.m.prepare(self.home,self.config,['claude'])
        self.assertEqual(p.read_text(),'keep existing service')

    def test_prefix_overlap_rejected_before_mutation(self):
        data=json.loads(self.config.read_text());data['projects']['beta']['unit_prefixes']=['alpha-child-']
        self.config.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'overlapping'):self.m.prepare(self.home,self.config,['claude'])
        self.assertEqual(list(self.home.iterdir()),[])

    def test_codex_preserves_native_settings_or_requires_supported_python(self):
        if self.m.tomllib is None:
            with self.assertRaisesRegex(ValueError,'Python 3.11'):self.m.prepare(self.home,self.config,['codex'])
            return
        text='model = "user-selected"\n[features]\nexample = true\n'
        command='python3 /path/to/cpu_enforcement.py hook --provider codex'
        once=self.m.codex_settings(text,command)
        self.assertEqual(once,self.m.codex_settings(once,command))
        parsed=self.m.tomllib.loads(once);self.assertEqual(parsed['model'],'user-selected')
        self.assertTrue(parsed['features']['example'])
        restored=self.m.codex_settings(once,command,remove=True)
        self.assertEqual(self.m.tomllib.loads(restored),self.m.tomllib.loads(text))

    def test_partial_removal_preserves_other_client_guardian(self):
        payload=self.home/'.local/share/token-efficiency-setup/cpu';payload.mkdir(parents=True)
        (payload/('.'+self.m.MARKER)).touch()
        p=self.home/'.codex/config.toml';p.parent.mkdir()
        p.write_text('# token-efficiency-setup/cpu/cpu_enforcement.py')
        with self.assertRaisesRegex(ValueError,'all installed CPU clients'):
            self.m.prepare(self.home,self.config,['claude'],remove=True)

    def test_ambiguous_worktree_roots_rejected_before_mutation(self):
        data=json.loads(self.config.read_text());data['projects']['beta']['roots']=[str(self.root/'alpha/nested')]
        self.config.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'worktree roots overlap'):
            self.m.prepare(self.home,self.config,['claude'])
        self.assertEqual(list(self.home.iterdir()),[])

    def test_unmanaged_controller_cannot_be_removed(self):
        with self.assertRaisesRegex(ValueError,'no managed CPU installation'):
            self.m.prepare(self.home,self.config,['claude'],remove=True)


if __name__=='__main__':unittest.main()
