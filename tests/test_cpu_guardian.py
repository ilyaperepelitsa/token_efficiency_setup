import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BIN=Path(__file__).resolve().parents[1]/'cpu'
sys.path.insert(0,str(BIN))
import cpu_guardian as broker


class Guardian(unittest.TestCase):
    def test_compact_and_legacy_waiting_processes_match_full_tickets(self):
        real_path=Path;first='abcdef123456'+'a'*20;second='fedcba654321'+'b'*20
        script=str(Path(broker.guard.__file__).resolve()).encode()
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            for pid,args in [(321,[b'python3',script,b'compact',first[:12].encode(),b'--',b'payload --ticket is data']),
                             (322,[b'python3',script,b'--config',b'/config',b'exec',b'--project',b'compact',b'--ticket',second.encode(),b'--command',b'payload'])]:
                p=directory/str(pid);p.mkdir();(p/'cmdline').write_bytes(b'\0'.join(args)+b'\0')
            def factory(*parts):return directory if parts==('/proc',) else real_path(*parts)
            with patch.object(broker,'Path',side_effect=factory):
                found=broker.waiting_pids({first,second})
                self.assertEqual(found,{first:321,second:322})
                collision=first[:12]+'c'*20
                self.assertNotIn(first,broker.waiting_pids({first,collision}))

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
