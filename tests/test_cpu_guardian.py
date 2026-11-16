import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

BIN=Path(__file__).resolve().parents[1]/'cpu'
sys.path.insert(0,str(BIN))
import cpu_guardian as broker


class Guardian(unittest.TestCase):
    def test_cpu_bitmap_preserves_exact_sparse_mask(self):
        self.assertEqual(broker.bitmap({0,2,9}),[5,2])

    def test_native_unit_is_session_proof_and_resource_only(self):
        text=(BIN/'templates/guardian.service.in').read_text().replace('@GUARDIAN@',str(BIN/'cpu_guardian.py'))
        for required in ['Restart=on-failure','/usr/bin/flock -n','cpu_guardian.py','MemoryMax=96M','MemorySwapMax=0','TasksMax=64']:
            self.assertIn(required,text)
        self.assertNotIn('nohup',text)

    def test_resource_rpc_contains_no_shell_or_code_execution(self):
        properties=[('PIDs','au',[123]),('AllowedCPUs','ay',[5]),('CPUAccounting','b',True)]
        with patch.object(broker.subprocess,'run') as call:
            broker.start_scope('cpu-exec-test.scope',properties)
        args=call.call_args.args[0]
        self.assertIn('StartTransientUnit',args)
        self.assertIn('PIDs',args)
        self.assertNotIn('ExecStart',args)
        self.assertNotIn('/bin/bash',args)

    def test_dead_parent_is_not_release_while_scope_populated(self):
        row={'pid':123,'start':'old','group':'/owned.scope'}
        with patch.object(broker.guard,'process_start',return_value=None), \
             patch.object(Path,'read_text',return_value='populated 1\nfrozen 0\n'):
            self.assertTrue(broker.scope_live(row))
        with patch.object(broker.guard,'process_start',return_value=None), \
             patch.object(Path,'read_text',return_value='populated 0\nfrozen 0\n'):
            self.assertFalse(broker.scope_live(row))

    def test_missing_cgroup_and_dead_pid_are_verified_drained(self):
        row={'pid':123,'start':'old','group':'/gone.scope'}
        with patch.object(broker.guard,'process_start',return_value=None), \
             patch.object(Path,'read_text',side_effect=FileNotFoundError):
            self.assertFalse(broker.scope_live(row))
        with patch.object(broker.guard,'process_start',return_value=None), \
             patch.object(Path,'read_text',side_effect=PermissionError):
            self.assertTrue(broker.scope_live(row))


if __name__=='__main__': unittest.main()
