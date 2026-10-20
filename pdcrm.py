"""Pawquanta Dynamic Compute Resource Manager: bounded workers, one submitter.

Temperature limits are conservative policy limits, not inferred hardware ratings.
Missing CPU telemetry disables CPU hashing. No drivers or elevated code installed.
"""
import hashlib
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import struct
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

DEFAULTS={'cpu_workers':0,'cpu_duty':.5,'gpu_duty':.3}

def memory_worker_limit():
    """Reserve host memory; refuse to spawn a process per core blindly."""
    try:
        if sys.platform=='win32':
            import ctypes
            class Memory(ctypes.Structure):
                _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(name,ctypes.c_ulonglong) for name in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
            value=Memory();value.length=ctypes.sizeof(value)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):raise OSError('Memory query failed')
            available=value.available
        elif sys.platform=='darwin':
            import re
            text=subprocess.check_output(['/usr/bin/vm_stat'],text=True,timeout=2)
            page=int(re.search(r'page size of (\d+)',text).group(1))
            available=sum(int(re.search(r'Pages '+name+r':\s+(\d+)',text).group(1)) for name in ('free','inactive','speculative'))*page
        else:available=os.sysconf('SC_AVPHYS_PAGES')*os.sysconf('SC_PAGE_SIZE')
        return max(0,min(64,int((available-1024**3)//(256*1024**2))))
    except Exception:return 0

def settings(profile):
    file=Path(profile)/'pdcrm.json'
    value={**DEFAULTS,**(json.loads(file.read_text()) if file.exists() else {})}
    if not file.exists():
        try:
            legacy=json.loads((Path(profile)/'gpu-performance.json').read_text())['duty_cycle']
            if type(legacy) in (int,float) and .05<=legacy<=.5:value['gpu_duty']=legacy
        except (OSError,ValueError,TypeError,KeyError):pass
    cores=value['cpu_workers']
    if type(cores) is not int or not 0<=cores<=min(64,os.cpu_count() or 1):raise ValueError('Invalid CPU worker count')
    for name in ('cpu_duty','gpu_duty'):
        if type(value[name]) not in (int,float) or not math.isfinite(value[name]) or not .05<=value[name]<=1:raise ValueError('Duty must be between 5% and 100%')
    return value

def save_settings(profile,value):
    folder=Path(profile);folder.mkdir(parents=True,exist_ok=True)
    temporary=folder/'pdcrm.new.json';temporary.write_text(json.dumps(value,indent=2))
    # Validate before replacing previously usable settings.
    cores=value.get('cpu_workers')
    if type(cores) is not int or not 0<=cores<=min(64,os.cpu_count() or 1):raise ValueError('Invalid CPU worker count')
    for key in ('cpu_duty','gpu_duty'):
        if type(value.get(key)) not in (int,float) or not math.isfinite(value[key]) or not .05<=value[key]<=1:raise ValueError('Invalid compute duty')
    temporary.replace(folder/'pdcrm.json')

def cpu_telemetry():
    if sys.platform=='darwin':
        from gpu_miner import telemetry
        return telemetry()  # Apple's system thermal pressure covers CPU and GPU.
    if sys.platform!='win32':raise RuntimeError('CPU thermal monitoring is unavailable on this platform')
    # Read an existing provider; never download/install a kernel driver implicitly.
    script=r"""$ErrorActionPreference='Stop'; $s = @(Get-CimInstance -Namespace root\LibreHardwareMonitor -ClassName Sensor | Where-Object { $_.SensorType -eq 'Temperature' -and $_.Identifier -match '^/(intelcpu|amdcpu)/' }); if ($s.Count -eq 0) { throw 'No CPU temperature sensors' }; $s | Select-Object Identifier,Value | ConvertTo-Json -Compress"""
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,text=True,timeout=4,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    rows=json.loads(result.stdout);rows=rows if isinstance(rows,list) else [rows]
    values=[float(row['Value']) for row in rows if row.get('Value') is not None]
    if not values or any(not math.isfinite(v) or not 0<v<120 for v in values):raise RuntimeError('CPU temperature readings invalid')
    return {'temperature_c':max(values),'source':'LibreHardwareMonitor CPU sensors'}

def cpu_decision(sample,paused=False):
    if 'thermal_state' in sample:
        state=sample['thermal_state']
        if type(state) is not int or state not in (0,1,2,3):raise ValueError('Invalid system thermal state')
        return 'stop' if state>=2 else 'pause' if state==1 else 'mine'
    temp=sample.get('temperature_c')
    if type(temp) not in (int,float) or not math.isfinite(temp) or not 0<temp<120:raise ValueError('Invalid CPU temperature')
    if temp>=85:return 'stop'
    if temp>=80 or paused and temp>70:return 'pause'
    return 'mine'

def cpu_chunk(prefix,target,start,end,seconds):
    """Hash only a bounded, non-overlapping nonce range. No wallet credentials."""
    deadline=time.monotonic()+seconds;count=0
    for nonce in range(start,end):
        digest=hashlib.sha256(hashlib.sha256(prefix+struct.pack('<I',nonce)).digest()).digest();count+=1
        if int.from_bytes(digest,'little')<=target:return nonce,count
        if count%256==0 and time.monotonic()>=deadline:break
    return None,count

def _cpu_worker(pipe):
    try:
        while True:
            job=pipe.recv()
            if job is None:return
            prefix,target,start,end,seconds,duty=job
            began=time.monotonic();result=cpu_chunk(prefix,target,start,end,seconds)
            time.sleep(max(0,(time.monotonic()-began)*(1/duty-1)))
            pipe.send(result)
    except (EOFError,BrokenPipeError):return
    finally:pipe.close()

class CPUFarm:
    def __init__(self,count):
        self.workers=[];context=mp.get_context('spawn')
        try:
            for _ in range(count):
                pipe,child=context.Pipe();process=context.Process(target=_cpu_worker,args=(child,),daemon=True)
                process.start();child.close();self.workers.append((pipe,process))
        except BaseException:self.close();raise

    def search(self,prefix,target,duty,stop):
        # GPU has the low half; CPU workers split the high half without overlap.
        stride=(2**31)//len(self.workers);results=[];total=0
        for i,(pipe,process) in enumerate(self.workers):
            start=2**31+i*stride;end=2**32 if i==len(self.workers)-1 else start+stride
            pipe.send((prefix,target,start,end,.20,duty))
        deadline=time.monotonic()+8
        for pipe,process in self.workers:
            while not pipe.poll(.05):
                if stop.exists() or time.monotonic()>deadline or not process.is_alive():
                    self.close();raise RuntimeError('CPU worker stopped or timed out')
            nonce,count=pipe.recv();total+=count
            if nonce is not None:results.append(nonce)
        return (results[0] if results else None),total

    def close(self):
        for pipe,process in self.workers:
            if process.is_alive():process.terminate()
            process.join(timeout=2);pipe.close()
        self.workers=[]

class DynamicSearch:
    """One coordinator submits blocks; CPU/GPU only search bounded headers."""
    def __init__(self,stop,gpu=None):
        self.stop=Path(stop);self.profile=self.stop.parent;self.gpu=gpu
        self.farm=None;self.count=0;self.pool=ThreadPoolExecutor(max_workers=2)
        self.shutdown=threading.Event();self.gate=threading.Event()
        self.cpu_enabled=False;self.cpu_state={'phase':'sensor_unavailable'};self.fault=None;self.cpu_hot=False
        self.cpu_hashes=0;self.gpu_hashes=0;self.checked=0
        self.monitor=threading.Thread(target=self._monitor,name='PDCRM-thermal',daemon=True);self.monitor.start()

    def _monitor(self):
        paused=False;cool_until=0
        while not self.shutdown.is_set():
            try:
                requested=settings(self.profile)['cpu_workers']>0
                if not requested:
                    self.gate.clear();self.cpu_state={'phase':'disabled'}
                    # If CPU heat was observed, retain the system pause until a
                    # real cool sample, even after CPU workers are disabled.
                    if self.cpu_hot:
                        sample=cpu_telemetry()
                        if cpu_decision(sample,True)=='mine' and time.monotonic()>=cool_until:self.cpu_hot=False
                else:
                    sample=cpu_telemetry();decision=cpu_decision(sample,paused)
                    if decision=='stop':cool_until=time.monotonic()+30
                    if decision=='mine' and time.monotonic()<cool_until:decision='pause'
                    paused=decision!='mine';self.cpu_hot=paused;self.cpu_state={**sample,'phase':decision,'checked_at':time.time()}
                    self.checked=time.monotonic()
                    if paused or self.gpu and self.gpu.paused:self.gate.clear()
                    else:self.gate.set()
            except Exception as error:
                self.gate.clear();self.cpu_state={'phase':'sensor_unavailable','message':'CPU hashing paused: verified CPU temperature unavailable. '+str(error)[:200]}
            self.shutdown.wait(.5)

    def _cpu_round(self,prefix,target,value):
        count=min(value['cpu_workers'],memory_worker_limit())
        if not count:
            if self.farm:self.farm.close();self.farm=None
            self.count=0;return None
        if not self.gate.is_set() or time.monotonic()-self.checked>5:return None
        if count!=self.count:
            if self.farm:self.farm.close()
            self.farm=CPUFarm(count) if count else None;self.count=count
        # Recheck after process startup; no work if the monitor became stale.
        if not self.gate.is_set() or time.monotonic()-self.checked>5:return None
        nonce,hashes=self.farm.search(prefix,target,value['cpu_duty'],self.stop)
        self.cpu_hashes+=hashes;return nonce

    def search(self,prefix,target,seconds=1):
        from gpu_miner import write_status
        value=settings(self.profile)
        # Detect the requested CPU sensor before work; the monitor supplies a
        # fresh gate thereafter. Work remains paused while it initializes.
        futures=[self.pool.submit(self._cpu_round,prefix,target,value)]
        if self.gpu:
            self.gpu.external_thermal_gate=lambda:not self.cpu_hot
            futures.append(self.pool.submit(self.gpu.search,prefix,target,.25))
        results=[future.result(timeout=10) for future in futures]
        if self.gpu:
            self.gpu_hashes=getattr(self.gpu,'total_hashes',0)
            # CPU load cannot continue while a monitored GPU is over its limits.
            if self.gpu.paused:self.gate.clear()
        write_status(self.profile/'pdcrm-status.json',{'updated_at':time.time(),'cpu':self.cpu_state,
            'cpu_workers_requested':value['cpu_workers'],'cpu_workers_allocated':self.count,'cpu_duty':value['cpu_duty'],'gpu_duty':value['gpu_duty'],
            'cpu_hashes':self.cpu_hashes,'gpu_hashes':self.gpu_hashes,'gpu_enabled':self.gpu is not None,
            'limits':{'cpu_pause_c':80,'cpu_resume_c':70,'cpu_stop_c':85,'gpu_pause_c':68,'gpu_resume_c':66,'gpu_stop_c':75},
            'policy':'Conservative limits; no inferred manufacturer rating. Sensor faults pause or stop mining.'})
        for nonce in results:
            if nonce is not None:
                digest=hashlib.sha256(hashlib.sha256(prefix+struct.pack('<I',nonce)).digest()).digest()
                if int.from_bytes(digest,'little')>target:raise RuntimeError('Compute worker returned invalid proof of work')
                return nonce
        if not any(n is not None for n in results):self.shutdown.wait(.2 if not self.gpu and not self.gate.is_set() else .02)
        return None

    def close(self):
        self.shutdown.set();self.gate.clear();self.monitor.join(timeout=5)
        self.pool.shutdown(wait=True,cancel_futures=True)
        if self.farm:self.farm.close()
