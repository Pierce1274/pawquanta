import hashlib
import json
from pathlib import Path
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import pdcrm

class ResourceTests(unittest.TestCase):
    def test_settings_and_thermal_hysteresis(self):
        with tempfile.TemporaryDirectory() as d:
            for v in [float('nan'),0,1.1,True]:
                with self.assertRaises(ValueError):pdcrm.save_settings(d,{'cpu_workers':0,'cpu_duty':v,'gpu_duty':.5})
            pdcrm.save_settings(d,{'cpu_workers':0,'cpu_duty':1,'gpu_duty':1})
            self.assertEqual(pdcrm.settings(d)['gpu_duty'],1)
        self.assertEqual(pdcrm.cpu_decision({'temperature_c':79}),'mine')
        self.assertEqual(pdcrm.cpu_decision({'temperature_c':80}),'pause')
        self.assertEqual(pdcrm.cpu_decision({'temperature_c':75},True),'pause')
        self.assertEqual(pdcrm.cpu_decision({'temperature_c':70},True),'mine')
        self.assertEqual(pdcrm.cpu_decision({'temperature_c':85}),'stop')
        with self.assertRaises(ValueError):pdcrm.cpu_decision({'temperature_c':float('nan')})

    def test_real_spawned_cpu_workers_validate_pow(self):
        with tempfile.TemporaryDirectory() as d:
            farm=pdcrm.CPUFarm(2)
            try:
                prefix=bytes(range(76));nonce,count=farm.search(prefix,2**256-1,1,Path(d)/'STOP')
                self.assertGreaterEqual(nonce,2**31);self.assertEqual(count,2)
                digest=hashlib.sha256(hashlib.sha256(prefix+struct.pack('<I',nonce)).digest()).digest()
                self.assertLessEqual(int.from_bytes(digest,'little'),2**256-1)
            finally:farm.close()

    def test_sensor_failure_blocks_cpu_but_gpu_still_runs(self):
        class GPU:
            paused=False;total_hashes=0
            def search(self,prefix,target,seconds):self.total_hashes+=1;return 0
        with tempfile.TemporaryDirectory() as d,patch.object(pdcrm,'cpu_telemetry',side_effect=RuntimeError('missing sensor')):
            pdcrm.save_settings(d,{'cpu_workers':1,'cpu_duty':.5,'gpu_duty':.5})
            with patch.object(pdcrm,'CPUFarm') as farm:
                worker=pdcrm.DynamicSearch(Path(d)/'STOP',GPU())
                try:
                    time.sleep(.05);self.assertEqual(worker.search(bytes(76),2**256-1),0)
                    self.assertFalse(worker.gate.is_set());farm.return_value.search.assert_not_called()
                finally:worker.close()

    def test_cpu_and_gpu_are_concurrent_and_cpu_heat_blocks_gpu(self):
        barrier=threading.Barrier(2)
        class GPU:
            paused=False;total_hashes=0
            def search(self,prefix,target,seconds):
                barrier.wait(timeout=3);self.total_hashes+=1;return 0
        class Farm:
            def __init__(self,count):pass
            def search(self,*args):barrier.wait(timeout=3);return 2**31,1
            def close(self):pass
        with tempfile.TemporaryDirectory() as d,patch.object(pdcrm,'CPUFarm',Farm),patch.object(pdcrm,'cpu_telemetry',return_value={'temperature_c':50}):
            pdcrm.save_settings(d,{'cpu_workers':1,'cpu_duty':.5,'gpu_duty':.5})
            gpu=GPU();worker=pdcrm.DynamicSearch(Path(d)/'STOP',gpu)
            try:
                self.assertTrue(worker.gate.wait(2));self.assertIsNotNone(worker.search(bytes(76),2**256-1))
                worker.cpu_hot=True;self.assertFalse(gpu.external_thermal_gate())
            finally:worker.close()

if __name__=='__main__':unittest.main()
