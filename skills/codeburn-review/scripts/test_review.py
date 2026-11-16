import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone

SCRIPT = Path(__file__).with_name('review.py')


class ReviewTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('review', SCRIPT)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.end = datetime(2026, 11, 16, 11, tzinfo=timezone.utc)

    def test_adjacent_windows_deduplicate_and_compare(self):
        p = self.root / 'main.jsonl'
        rows = []
        for ident, at, output in [('a', '10:40', 10), ('b', '10:50', 20), ('b', '10:50', 20)]:
            rows.append({'type': 'assistant', 'timestamp': '2026-11-16T'+at+':00Z',
                'message': {'id': ident, 'usage': {'input_tokens': 2,
                    'cache_creation_input_tokens': 100, 'cache_read_input_tokens': 200,
                    'output_tokens': output}, 'content': [{'type':'text','text':'PRIVATE'}]}})
        p.write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
        r = self.m.compare('claude', p, self.end)
        self.assertEqual(r['current']['output'], 20)
        self.assertEqual(r['previous']['output'], 10)
        self.assertEqual(r['delta_pct']['output'], 100)
        self.assertEqual(r['current']['responses'], 1)
        self.assertNotIn('PRIVATE', json.dumps(r))
        self.assertIsNone(r['accepted_batches'])

    def test_codex_response_records_not_token_count_twins(self):
        p = self.root / 'codex.jsonl'
        usage = {'input_tokens':100,'cached_input_tokens':80,
                 'output_tokens':12,'reasoning_output_tokens':7}
        record = {'timestamp':'2026-11-16T10:50:00Z','type':'token_usage_record',
                  'payload':{'response_id':'resp_a','usage':usage}}
        twin = {'timestamp':record['timestamp'],'type':'event_msg',
                'payload':{'type':'token_count','info':{'last_token_usage':usage}}}
        p.write_text('\n'.join(json.dumps(r) for r in [record,record,twin])+'\n')
        r = self.m.compare('codex',p,self.end)
        self.assertEqual(r['current']['responses'],1)
        self.assertEqual(r['current']['new_input'],20)
        self.assertEqual(r['current']['cached'],80)
        self.assertEqual(r['current']['output'],12)

    def test_hook_is_main_only_rate_limited_and_never_blocks(self):
        body={'session_id':'test','transcript_path':str(self.root/'main.jsonl'),
              'hook_event_name':'PostToolUse'}
        called=[]
        def report():
            called.append(1)
            return {'current':{'responses':1}}
        self.assertIsNone(self.m.reminder(body,self.root,1000,report))
        self.assertIsNone(self.m.reminder(body,self.root,1899,report))
        worker={**body,'agent_id':'worker'}
        self.assertIsNone(self.m.reminder(worker,self.root,1900,report))
        out=self.m.reminder(body,self.root,1900,report)
        self.assertIn('additionalContext',out['hookSpecificOutput'])
        self.assertNotIn('decision',out)
        self.assertNotIn('permissionDecision',json.dumps(out))
        self.assertEqual(len(called),1)
        self.assertIsNone(self.m.reminder(body,self.root,1901,report))

    def test_zero_previous_and_partial_line_do_not_invent_improvement(self):
        p=self.root/'empty.jsonl';p.write_text('{partial')
        r=self.m.compare('claude',p,self.end)
        self.assertIsNone(r['delta_pct']['cached'])
        self.assertFalse(r['data_complete'])

    def test_non_usage_metadata_without_timestamp_is_not_corruption(self):
        p=self.root/'metadata.jsonl'
        p.write_text(json.dumps({'type':'file-history-snapshot','snapshot':{}})+'\n')
        r=self.m.compare('claude',p,self.end)
        self.assertTrue(r['data_complete'])

    def test_dense_report_has_hard_cap_and_all_metrics(self):
        p=self.root/'empty.jsonl';p.write_text('')
        report=self.m.compare('claude',p,self.end)
        report['largest_contexts']=[{'agent':'very-long-worker-name-'*20,
            'context':577123,'responses':150,'cache_write':1000,'output':1000}]*3
        text=self.m.compact(report,'/tmp/exact-report.json')
        self.assertLessEqual(len(text),1000)
        for item in ['new','write','cached','output','calls','ctx','complete','accepted','cpu',
                     'prev','now','delta','/tmp/exact-report.json']:
            self.assertIn(item,text)

    def test_injected_reminder_is_capped_including_instructions(self):
        p=self.root/'empty.jsonl';p.write_text('')
        report=lambda:self.m.compare('claude',p,self.end)
        body={'session_id':'dense','transcript_path':str(p),'hook_event_name':'PostToolUse'}
        self.m.reminder(body,self.root,1000,report)
        result=self.m.reminder(body,self.root,1900,report)
        self.assertLessEqual(len(result['hookSpecificOutput']['additionalContext']),1000)


if __name__=='__main__':
    unittest.main()
