import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from policy import rejection

class PolicyTests(unittest.TestCase):
    def check(self, mode='protected', **updates):
        c = dict(job_id='B', command_id='abc', dose=6, issued_at=100)
        c.update(updates)
        return rejection(c, mode=mode, job_id='B', phase='READY', now=100.2, seen=False)
    def test_good(self): self.assertIsNone(self.check())
    def test_stale_weak(self): self.assertIsNone(self.check('weak', job_id='A', issued_at=90, dose=10))
    def test_wrong_job(self): self.assertEqual(self.check(job_id='A'), 'wrong_job')
    def test_expired(self): self.assertEqual(self.check(issued_at=90), 'expired')
    def test_future(self): self.assertEqual(self.check(issued_at=110), 'future_timestamp')
    def test_nonfinite(self): self.assertEqual(self.check(dose=float('nan')), 'invalid_dose')
    def test_limit(self): self.assertEqual(self.check(dose=12), 'dose_out_of_lab_range')
    def test_duplicate(self):
        c = dict(job_id='B', command_id='abc', dose=6, issued_at=100)
        self.assertEqual(rejection(c, mode='protected', job_id='B', phase='READY', now=100.2, seen=True), 'duplicate_command')
    def test_busy(self):
        c = dict(job_id='B', command_id='abc', dose=6, issued_at=100)
        self.assertEqual(rejection(c, mode='weak', job_id='B', phase='DISPENSING', now=100.2, seen=False), 'not_ready')

if __name__ == '__main__': unittest.main()
