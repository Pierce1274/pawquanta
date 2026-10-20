import json
from pathlib import Path
import tempfile
import unittest
from core_runtime import MAIN_GENESIS
import mining_schedule as schedule

class MiningScheduleTests(unittest.TestCase):
    def test_private_schedule_preserves_deadline_and_manual_cancellation(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(schedule.read(folder))
            value={'genesis':MAIN_GENESIS,'resume_at_utc':1900000000,'state':'paused'}
            schedule.update(folder,value,'paused')
            self.assertEqual(schedule.read(folder)['resume_at_utc'],1900000000)
            schedule.cancel(folder);self.assertEqual(schedule.read(folder)['state'],'cancelled')
            value['genesis']='wrong';schedule.update(folder,value,'paused')
            with self.assertRaises(ValueError):schedule.read(folder)

if __name__=='__main__':unittest.main()
