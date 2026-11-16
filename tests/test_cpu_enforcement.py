import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'cpu/cpu_enforcement.py'
sys.path.insert(0, str(SOURCE.parent))


class Enforcement(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('cpu_enforcement', SOURCE)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.table = self.root / 'CPU.md'
        self.table.write_text('Logical CPUs: 6\nSystem reserve: 4\nProject CPU limit: 5\n'
            '| Project | Count | Reserved | Active | Borrowed |\n| --- | --- | --- | --- | --- |\n'
            '| alpha | 2 | 0,1 | true | - |\n| beta | 2 | 2,3 | false | - |\n')
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps({'file': str(self.table), 'runtime': str(self.root/'state'),
            'projects': {'alpha': {'roots': [str(self.root/'alpha')], 'unit_prefixes': ['alpha-']},
                         'beta': {'roots': [str(self.root/'beta')], 'unit_prefixes': ['beta-']}}}))
        self.cfg = self.m.load_config(self.config)

    def test_prefix_and_worktree_identification(self):
        self.assertEqual(self.m.identify(self.cfg, 'alpha-compile.service', {}), 'alpha')
        self.assertEqual(self.m.identify(self.cfg, 'random.service',
            {'WorkingDirectory': str(self.root/'beta/build')}), 'beta')
        self.assertIsNone(self.m.identify(self.cfg, 'other.service',
            {'WorkingDirectory': str(self.root/'alphabet')}))

    def test_admission_rejects_inactive_host_and_stale_masks(self):
        with self.assertRaises(ValueError): self.m.allowed(self.cfg, 'beta', {2,3}, set())
        with self.assertRaises(ValueError): self.m.allowed(self.cfg, 'alpha', set(range(6)), {4})
        with self.assertRaises(ValueError): self.m.allowed(self.cfg, 'alpha', set(range(6)), {0,2})
        self.assertEqual(self.m.allowed(self.cfg, 'alpha', {0,1,2}, {0}), {0})
        with self.assertRaises(ValueError): self.m.allowed(self.cfg, 'alpha', {2,3}, set())

    def test_reservation_change_is_read_again_not_cached(self):
        self.assertEqual(self.m.allowed(self.cfg, 'alpha', set(range(6)), set()), {0,1})
        self.table.write_text(self.table.read_text().replace('| alpha | 2 | 0,1', '| alpha | 1 | 1'))
        self.assertEqual(self.m.allowed(self.cfg, 'alpha', set(range(6)), set()), {1})
        with self.assertRaises(ValueError): self.m.allowed(self.cfg, 'alpha', set(range(6)), {0})

    def test_live_waiter_blocks_inactive_and_loan_release(self):
        holder = {'project': 'alpha', 'unit': 'alpha-waiter.service', 'cpus': [0], 'state': 'active'}
        with patch.object(self.m, 'holders', return_value=[holder]):
            with self.assertRaises(ValueError): self.m.assert_drained(self.cfg, 'alpha', {0})
            self.m.assert_drained(self.cfg, 'alpha', {1})

    def test_old_allocation_still_live_blocks_new_owner(self):
        holders = [{'project': 'beta', 'unit': 'beta-old.service', 'cpus': [0], 'state': 'active'}]
        with self.assertRaises(ValueError): self.m.no_conflicts('alpha', {0,1}, holders)
        self.m.no_conflicts('alpha', {1}, holders)

    def test_restart_rechecks_and_properties_only_narrow(self):
        info = {'EffectiveCPUs': '0-3', 'AllowedCPUs': '0', 'WorkingDirectory': str(self.root/'alpha')}
        with patch.object(self.m, 'unit_info', return_value=info), \
             patch.object(self.m, 'holders', return_value=[]), \
             patch.object(self.m, 'set_mask') as setter:
            result = self.m.admit(self.cfg, 'alpha-test.service')
            self.assertEqual(result, {0})
            setter.assert_called_once_with('alpha-test.service', {0})
            self.table.write_text(self.table.read_text().replace('| alpha | 2 | 0,1', '| alpha | 1 | 1'))
            with self.assertRaises(ValueError): self.m.admit(self.cfg, 'alpha-test.service')

    def test_hook_wraps_multiline_shell_without_changing_arguments(self):
        command = "python3 - <<'PY'\nprint('literal $HOME; `x`')\nPY"
        body = {'tool_name': 'Bash', 'hook_event_name': 'PreToolUse',
                'cwd': str(self.root/'alpha'), 'tool_input': {'command': command, 'timeout': 123}}
        result = self.m.pre_hook(self.cfg, body, 'claude')['hookSpecificOutput']
        self.assertNotIn('permissionDecision', result)
        self.assertEqual(result['updatedInput']['timeout'], 123)
        args = __import__('shlex').split(result['updatedInput']['command'])
        self.assertEqual(args[args.index('--command')+1], command)
        self.assertEqual(self.m.pre_hook(self.cfg, body, 'codex')['hookSpecificOutput']['permissionDecision'], 'allow')

    def test_hook_inactive_blocks_execution_but_allows_standalone_activation(self):
        body = {'tool_name': 'Bash', 'cwd': str(self.root/'beta'), 'tool_input': {'command': 'make -j2'}}
        self.assertEqual(self.m.pre_hook(self.cfg, body, 'claude')['hookSpecificOutput']['permissionDecision'], 'deny')
        body['tool_input']['command'] = f'python3 {SOURCE.parent}/cpu-reservations.py --file {self.table} --project beta active'
        result=self.m.pre_hook(self.cfg, body, 'claude')
        self.assertIn('updatedInput',result['hookSpecificOutput'])
        self.assertTrue(self.m.reservations.status(self.table)['beta']['active'])
        self.table.write_text(self.table.read_text().replace('| beta | 2 | 2,3 | true','| beta | 2 | 2,3 | false'))
        body['tool_input']['command'] += ' && make -j2'
        self.assertEqual(self.m.pre_hook(self.cfg, body, 'claude')['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_bad_table_blocks_project_tools_but_not_unrelated_projects(self):
        self.table.write_text('broken')
        body = {'tool_name': 'Bash', 'cwd': str(self.root/'alpha'), 'tool_input': {'command': 'make'}}
        self.assertEqual(self.m.pre_hook(self.cfg, body, 'claude')['hookSpecificOutput']['permissionDecision'], 'deny')
        body['cwd'] = str(self.root/'unrelated')
        self.assertEqual(self.m.pre_hook(self.cfg, body, 'claude'), {})

    def test_usage_counts_only_owned_cpu_time(self):
        previous = {'time': 0, 'usage': {'a': {'project':'alpha','cpu_ns':2_000_000_000}}}
        current = {'time': 60, 'usage': {'a': {'project':'alpha','cpu_ns':62_000_000_000},
                                       'b': {'project':'beta','cpu_ns':0}}}
        result = self.m.utilization(previous, current)
        self.assertAlmostEqual(result['alpha']['cpu_equivalents'], 1.0)
        self.assertEqual(result['beta']['cpu_equivalents'], 0)
        current['usage'] = {}
        self.assertFalse(self.m.utilization(previous,current)['alpha']['complete'])

    def test_review_requires_real_evidence_and_next_action(self):
        with self.assertRaises(ValueError): self.m.review(self.cfg, 'alpha', 'dependency', '', self.root/'missing')
        evidence=self.root/'lane.md';evidence.write_text('Blocked on integration lock; next batch queued.')
        self.m.review(self.cfg, 'alpha', 'dependency', 'run batch after integration lock releases', evidence)
        review=json.loads((self.cfg['runtime']/'alpha.review.json').read_text())
        self.assertIn('next',review)

    def test_worker_does_not_run_separate_utilization_review(self):
        body={'agent_id':'worker','cwd':str(self.root/'alpha'),'hook_event_name':'PostToolUse'}
        with patch.object(self.m,'sample') as sampler:
            self.assertEqual(self.m.feedback_hook(self.cfg,body),{})
            sampler.assert_not_called()

    def test_systemd_249_queued_jobs_table_is_supported(self):
        rows=self.m.queued_jobs('829555 alpha-next.service start waiting\n737762 other.service stop running\n')
        self.assertEqual(rows[0]['unit'],'alpha-next.service')
        self.assertEqual(rows[0]['type'],'start')
        self.assertEqual(self.m.queued_jobs('[{"unit":"alpha-next.service","type":"start"}]'),
                         [{'unit':'alpha-next.service','type':'start'}])

    def test_live_census_cache_invalidated_immediately_by_table_change(self):
        with patch.object(self.m,'holders',return_value=[]) as live:
            self.m.checked_conflicts(self.cfg,'alpha',{0})
            self.m.checked_conflicts(self.cfg,'alpha',{0})
            self.assertEqual(live.call_count,1)
            self.table.write_text(self.table.read_text().replace('| alpha | 2 | 0,1','| alpha | 1 | 1'))
            live.return_value=[{'project':'beta','unit':'beta-still-live.service','cpus':[1]}]
            with self.assertRaises(ValueError): self.m.checked_conflicts(self.cfg,'alpha',{1})
            self.assertEqual(live.call_count,2)

    def test_wrong_owner_and_explicit_scope_escape_are_rejected(self):
        body={'tool_name':'Bash','cwd':str(self.root/'alpha'),'tool_input':{}}
        for command in ['systemd-run --user --scope make',
                        'systemd-run --user --unit=beta-work make',
                        f'python3 {SOURCE.parent}/cpu-reservations.py --file {self.table} --project beta inactive']:
            body['tool_input']['command']=command
            self.assertEqual(self.m.pre_hook(self.cfg,body,'claude')['hookSpecificOutput']['permissionDecision'],'deny')
        body['tool_input']['command']='cpu-enforce audit'
        body['cwd']=str(self.root/'beta')
        with patch.object(self.m,'sample',return_value={'projects':{}}):
            self.assertIn('updatedInput',self.m.pre_hook(self.cfg,body,'claude')['hookSpecificOutput'])

    def test_due_review_blocks_stop_until_evidenced_acknowledgement(self):
        self.cfg['runtime'].mkdir()
        state=self.cfg['runtime']/'alpha.feedback.json'
        now=time.time()
        self.m.atomic(state,{'last':now-901,'pending':False})
        body={'cwd':str(self.root/'alpha'),'hook_event_name':'PostToolUse'}
        with patch.object(self.m.time,'time',return_value=now), \
             patch.object(self.m,'sample',return_value={'projects':{'alpha':{'active':True,'available':2,'cpu_equivalents':0.5}}}):
            response=self.m.feedback_hook(self.cfg,body)
            self.assertLess(len(response['hookSpecificOutput']['additionalContext']),600)
            body['hook_event_name']='Stop'
            self.assertEqual(self.m.feedback_hook(self.cfg,body)['decision'],'block')
            body['stop_hook_active']=True
            self.assertEqual(self.m.feedback_hook(self.cfg,body)['decision'],'block')
        evidence=self.root/'lane.md';evidence.write_text('Waiting on a live integration lock; next target identified.')
        self.m.review(self.cfg,'alpha','lock','launch target when integration lock releases',evidence)
        self.assertEqual(self.m.feedback_hook(self.cfg,body),{})
        with self.assertRaises(ValueError):
            self.m.review(self.cfg,'alpha','lock','retry',self.table)

    def test_stop_catches_due_review_without_a_recent_post_tool(self):
        self.cfg['runtime'].mkdir()
        self.m.atomic(self.cfg['runtime']/'alpha.feedback.json',{'last':time.time()-901,'pending':False})
        body={'cwd':str(self.root/'alpha'),'hook_event_name':'Stop'}
        with patch.object(self.m,'sample',return_value={'projects':{'alpha':{'active':True}}}):
            self.assertEqual(self.m.feedback_hook(self.cfg,body)['decision'],'block')

    def test_broken_configuration_blocks_registered_root_only(self):
        self.config.write_text('broken')
        (self.root/'roots.json').write_text(json.dumps([str(self.root/'alpha')]))
        for directory,code in [('alpha',2),('unrelated',0)]:
            body={'tool_name':'Bash','hook_event_name':'PreToolUse','cwd':str(self.root/directory),
                  'tool_input':{'command':'pwd'}}
            p=subprocess.run([sys.executable,str(SOURCE),'--config',str(self.config),'hook','--provider','codex'],
                input=json.dumps(body),capture_output=True,text=True)
            self.assertEqual(p.returncode,code)


if __name__=='__main__': unittest.main()
