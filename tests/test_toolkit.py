import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


def module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.m=module('installer',ROOT/'scripts/install.py')
        self.tmp=tempfile.TemporaryDirectory(prefix='efficiency test ')
        self.addCleanup(self.tmp.cleanup);self.home=Path(self.tmp.name)

    def test_dry_run_writes_nothing(self):
        before=list(self.home.iterdir())
        self.m.install(self.home,['claude','codex'],True,True)
        self.assertEqual(before,list(self.home.iterdir()))

    def test_idempotent_hook_preserves_settings_and_launcher_handles_spaces(self):
        p=self.home/'.claude/settings.json';p.parent.mkdir()
        old={'model':'chosen-by-user','permissions':{'deny':['example']},
             'hooks':{'PostToolUse':[{'matcher':'Edit','hooks':[{'type':'command','command':'other-hook'}]}]}}
        p.write_text(json.dumps(old))
        for _ in range(2):
            self.m.install(self.home,['claude','codex'],True)
        d=json.loads(p.read_text())
        self.assertEqual(d['model'],old['model']);self.assertEqual(d['permissions'],old['permissions'])
        self.assertEqual(len(d['hooks']['PostToolUse']),2)
        self.assertEqual(d['hooks']['PostToolUse'][0],old['hooks']['PostToolUse'][0])
        result=subprocess.run([str(self.home/'.local/bin/codeburn-review'),'--help'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.m.install(self.home,['claude','codex'],remove=True)
        self.assertEqual(json.loads(p.read_text()),old)
        self.assertFalse((self.home/'.claude/skills/codeburn-review').exists())

    def test_conflicting_skill_is_preserved(self):
        p=self.home/'.claude/skills/codeburn-review';p.mkdir(parents=True)
        (p/'mine').write_text('keep')
        with self.assertRaises(ValueError):self.m.install(self.home,['claude'])
        self.assertEqual((p/'mine').read_text(),'keep')


class PublicContentTests(unittest.TestCase):
    def test_secret_and_path_patterns_do_not_print_values(self):
        m=module('privacy',ROOT/'scripts/check_public_content.py')
        self.assertIn('API key shape',m.inspect(Path('example.txt'),'sk-'+'A'*40))
        self.assertIn('personal absolute path',m.inspect(Path('example.txt'),'/home/'+'private-user/work'))
        self.assertEqual(m.inspect(Path('example.md'),'Use ~/.config or /path/to/worktree.'),[])


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.m=module('evidence',ROOT/'scripts/check_evidence.py')
        self.data=json.loads((ROOT/'data/anonymized-observations.json').read_text())

    def test_only_anonymous_aggregates_and_reproducible_arithmetic(self):
        changes=self.m.validate(self.data)
        self.assertEqual(changes, {'responses':9.9,'new_input_and_writes':-4.9,
                                  'cached_input':-35.6,'output':35.7})
        self.assertFalse(self.data['workloads_matched'])
        self.assertFalse(self.data['accepted_work_comparison_available'])

    def test_identifying_fields_and_free_text_are_rejected(self):
        self.data['usage']['before']['project_name']='example'
        with self.assertRaises(ValueError):self.m.validate(self.data)
        del self.data['usage']['before']['project_name']
        self.data['lead_contexts'][0]['sample']='identifying-label'
        with self.assertRaises(ValueError):self.m.validate(self.data)


def load_tests(loader, tests, pattern):
    review=module('review_tests',ROOT/'skills/codeburn-review/scripts/test_review.py')
    tests.addTests(loader.loadTestsFromModule(review))
    return tests
