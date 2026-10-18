import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from gpu_miner import GPUWorker,thermal_state

class SafetyTests(unittest.TestCase):
    def test_hysteresis_and_hard_stops(self):
        def state(t,p=30,paused=False):return thermal_state({'temperature_c':t,'power_w':p},paused)
        self.assertEqual(state(63),'mine')
        self.assertEqual(state(68),'pause')
        self.assertEqual(state(65,paused=True),'pause')
        self.assertEqual(state(62,paused=True),'mine')
        self.assertEqual(state(75),'stop')
        self.assertEqual(state(60,65),'stop')
        self.assertEqual(state(60,50),'pause')

    def test_sensor_failure_closes_worker(self):
        worker=GPUWorker.__new__(GPUWorker);worker.process=None
        with patch('gpu_miner.telemetry',side_effect=RuntimeError('sensor missing')),patch.object(worker,'close') as close:
            with self.assertRaises(RuntimeError):worker.sample(force=True)
            close.assert_called_once()

    @unittest.skipUnless(os.environ.get('PQUA_TEST_GPU')=='1','Explicit physical GPU test only')
    def test_actual_gpu_matches_cpu_and_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            stop=Path(directory)/'STOP';worker=GPUWorker(stop)
            try:
                for start in (0,255,65535,2**32-64):
                    prefix=os.urandom(76);raw=worker.hashes(prefix,start,64)
                    for offset in range(64):
                        value=prefix+struct.pack('<I',start+offset)
                        self.assertEqual(raw[offset*32:offset*32+32],hashlib.sha256(hashlib.sha256(value).digest()).digest())
                self.assertIsNotNone(worker.search(bytes(range(76)),2**256-1))
                stop.touch();self.assertIsNone(worker.search(bytes(range(76)),2**256-1))
                print(json.dumps({'physical_gpu_test':True,'device':worker.device,'sample':worker.last_sample}))
            finally:worker.close()

if __name__=='__main__':unittest.main()
