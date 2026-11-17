import importlib.util
from pathlib import Path
import unittest


class Status(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / 'cpu/cpu_status.py'
        spec = importlib.util.spec_from_file_location('cpu_status', path)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.latest = {'time': 1000, 'measured_at': 1000, 'seconds': 61,
            'projects': {'alpha': {'active': True, 'available': 2,
                'cpu_equivalents': 1.25, 'complete': True}},
            'holders': [{'project': 'alpha', 'cpus': [0, 1]}]}

    def show(self, **kwargs):
        return self.m.render('alpha', {0, 1}, self.latest, now=1010, **kwargs)

    def test_guard_and_owned_usage_are_separate(self):
        text = self.show(guardian=True)
        self.assertIn('guard:on', text)
        self.assertIn('scopes:ok', text)
        self.assertIn('~1.2/2 cores', text)
        self.assertNotIn('progress', text)

    def test_stopped_guard_stale_and_conflicting_scopes_are_visible(self):
        self.assertIn('guard:OFF', self.show(guardian=False))
        self.latest['time'] = 0
        self.assertIn('stale', self.show(guardian=True))
        self.latest['time'] = 1000
        self.latest['holders'][0]['cpus'] = [2]
        self.assertIn('scopes:VIOLATION', self.show(guardian=True))

    def test_missing_or_incomplete_measurements_never_look_exact(self):
        row = self.latest['projects']['alpha']
        row['complete'] = False
        self.assertIn('partial', self.show(guardian=True))
        row['cpu_equivalents'] = None
        self.assertIn('?/2 cores', self.show(guardian=True))
        row['cpu_equivalents'] = float('nan')
        self.assertIn('?/2 cores', self.show(guardian=True))
        row['cpu_equivalents'] = 1.25
        self.latest['seconds'] = 2
        self.assertIn('?/2 cores', self.show(guardian=True))

    def test_unknown_or_changed_capacity_never_looks_verified(self):
        self.latest['holders'] = []
        self.assertIn('scopes:none', self.show(guardian=True))
        self.latest['projects']['alpha']['available'] = 3
        self.assertIn('allocation changed', self.show(guardian=True))

    def test_old_measurement_is_not_made_fresh_by_status_reads(self):
        self.latest['measured_at'] = 0
        self.assertIn('stale', self.show(guardian=True))


if __name__ == '__main__':
    unittest.main()
