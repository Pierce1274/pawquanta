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
    def test_duty_limit_rejects_unbounded_settings(self):
        from gpu_miner import mining_duty
        with tempfile.TemporaryDirectory() as directory:
            stop=Path(directory)/'STOP';setting=stop.with_name('gpu-performance.json')
            self.assertEqual(mining_duty(stop),.10)
            for value in (True,-1,0,1,float('nan'),'fast'):
                setting.write_text(json.dumps({'duty_cycle':value}))
                self.assertEqual(mining_duty(stop),.10)
            setting.write_text(json.dumps({'duty_cycle':.30}))
            self.assertEqual(mining_duty(stop),.30)
    def test_status_reader_lock_is_not_a_mining_fault(self):
        from gpu_miner import write_status
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(Path,'replace',side_effect=PermissionError('reader lock')),patch('gpu_miner.time.sleep'):
                self.assertFalse(write_status(Path(directory)/'status.json',{'phase':'mine'}))

    def test_hot_gpu_resumes_only_after_safe_reading_and_cooldown(self):
        with tempfile.TemporaryDirectory() as directory:
            worker=GPUWorker.__new__(GPUWorker);worker.process=None;worker.paused=False;worker.checked=0;worker.cool_until=0
            worker.state_file=Path(directory)/'status.json';worker.latch=Path(directory)/'LATCH';worker.last_sample=None;worker.stop_file=Path(directory)/'STOP'
            readings=[{'temperature_c':75,'power_w':30},{'temperature_c':65,'power_w':30},{'temperature_c':65,'power_w':30}]
            with patch('gpu_miner.telemetry',side_effect=readings),patch('gpu_miner.time.monotonic',side_effect=[100,110,131]):
                worker.sample(force=True);self.assertTrue(worker.paused)
                worker.sample(force=True);self.assertTrue(worker.paused)
                worker.sample(force=True);self.assertFalse(worker.paused)
            self.assertFalse(worker.latch.exists())

    def test_idle_deadline_crossing_never_sleeps_negative(self):
        with tempfile.TemporaryDirectory() as directory:
            worker=GPUWorker.__new__(GPUWorker);worker.process=None
            worker.stop_file=Path(directory)/'STOP'
            from unittest.mock import Mock
            worker.pipe=Mock();worker.receive=Mock(return_value=('hashes',b'0'*32))
            ticks=iter([0,.1,.11,.2,2,2])
            with patch('gpu_miner.time.monotonic',side_effect=lambda:next(ticks,2)),patch('gpu_miner.time.sleep') as sleep:
                self.assertEqual(len(worker.hashes(b'0'*76,0,1)),32)
                for call in sleep.call_args_list:self.assertGreaterEqual(call.args[0],0)

    def test_hysteresis_and_hard_stops(self):
        def state(t,p=30,paused=False):return thermal_state({'temperature_c':t,'power_w':p},paused)
        self.assertEqual(state(63),'mine')
        self.assertEqual(state(68),'pause')
        self.assertEqual(state(67,paused=True),'pause')
        self.assertEqual(state(66,paused=True),'mine')
        self.assertEqual(state(75),'stop')
        self.assertEqual(state(60,65),'stop')
        self.assertEqual(state(60,50),'pause')
        self.assertEqual(thermal_state({'temperature_c':60,'power_w':100,'power_limit_w':575}),'mine')
        self.assertEqual(thermal_state({'thermal_state':0}),'mine')
        self.assertEqual(thermal_state({'thermal_state':1}),'pause')
        self.assertEqual(thermal_state({'thermal_state':2}),'stop')

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
                if os.name=='nt':
                    prefix=bytes(range(76))
                    scores=[int.from_bytes(hashlib.sha256(hashlib.sha256(prefix+struct.pack('<I',n)).digest()).digest(),'little') for n in range(256)]
                    best=min(range(256),key=scores.__getitem__)
                    worker.pipe.send((prefix,0,256,scores[best]));self.assertEqual(worker.receive(3),('nonce',best))
                    worker.pipe.send((prefix,0,256,scores[best]-1));self.assertEqual(worker.receive(3),('nonce',None))
                stop.touch();self.assertIsNone(worker.search(bytes(range(76)),2**256-1))
                print(json.dumps({'physical_gpu_test':True,'device':worker.device,'sample':worker.last_sample}))
            finally:worker.close()

if __name__=='__main__':unittest.main()
