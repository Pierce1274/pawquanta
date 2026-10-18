"""Bounded NVIDIA OpenCL SHA256d worker with a fail-closed thermal watchdog.

No clock, voltage, fan, driver or power-limit changes. GPU code runs in a
disposable child process; wallet credentials never enter that child.
"""
import json
import multiprocessing as mp
import os
from pathlib import Path
import struct
import subprocess
import time
import hashlib
import sys

def metal_executable():
    base=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    return base/'Pawquanta-Metal'

K = '428a2f98 71374491 b5c0fbcf e9b5dba5 3956c25b 59f111f1 923f82a4 ab1c5ed5 d807aa98 12835b01 243185be 550c7dc3 72be5d74 80deb1fe 9bdc06a7 c19bf174 e49b69c1 efbe4786 0fc19dc6 240ca1cc 2de92c6f 4a7484aa 5cb0a9dc 76f988da 983e5152 a831c66d b00327c8 bf597fc7 c6e00bf3 d5a79147 06ca6351 14292967 27b70a85 2e1b2138 4d2c6dfc 53380d13 650a7354 766a0abb 81c2c92e 92722c85 a2bfe8a1 a81a664b c24b8b70 c76c51a3 d192e819 d6990624 f40e3585 106aa070 19a4c116 1e376c08 2748774c 34b0bcb5 391c0cb3 4ed8aa4a 5b9cca4f 682e6ff3 748f82ee 78a5636f 84c87814 8cc70208 90befffa a4506ceb bef9a3f7 c67178f2'
SOURCE = '__constant uint K[64]={' + ','.join('0x'+x+'U' for x in K.split()) + '};' + r'''
uint rr(uint x,uint n){return (x>>n)|(x<<(32-n));}
void init(uint *s){s[0]=0x6a09e667;s[1]=0xbb67ae85;s[2]=0x3c6ef372;s[3]=0xa54ff53a;s[4]=0x510e527f;s[5]=0x9b05688c;s[6]=0x1f83d9ab;s[7]=0x5be0cd19;}
void compress(uint *s,uint *w){
 for(int i=16;i<64;i++)w[i]=w[i-16]+(rr(w[i-15],7)^rr(w[i-15],18)^(w[i-15]>>3))+w[i-7]+(rr(w[i-2],17)^rr(w[i-2],19)^(w[i-2]>>10));
 uint a=s[0],b=s[1],c=s[2],d=s[3],e=s[4],f=s[5],g=s[6],h=s[7];
 for(int i=0;i<64;i++){uint t=h+(rr(e,6)^rr(e,11)^rr(e,25))+((e&f)^(~e&g))+K[i]+w[i];uint u=(rr(a,2)^rr(a,13)^rr(a,22))+((a&b)^(a&c)^(b&c));h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u;}
 s[0]+=a;s[1]+=b;s[2]+=c;s[3]+=d;s[4]+=e;s[5]+=f;s[6]+=g;s[7]+=h;
}
__kernel void hash_headers(__global const uchar *prefix,uint start,__global uchar *out){
 uint id=get_global_id(0),nonce=start+id,w[64],s[8];init(s);
 for(int i=0;i<16;i++)w[i]=((uint)prefix[i*4]<<24)|((uint)prefix[i*4+1]<<16)|((uint)prefix[i*4+2]<<8)|prefix[i*4+3];
 compress(s,w);for(int i=0;i<64;i++)w[i]=0;
 for(int i=0;i<3;i++)w[i]=((uint)prefix[64+i*4]<<24)|((uint)prefix[65+i*4]<<16)|((uint)prefix[66+i*4]<<8)|prefix[67+i*4];
 w[3]=((nonce&255)<<24)|((nonce&65280)<<8)|((nonce>>8)&65280)|(nonce>>24);w[4]=0x80000000;w[15]=640;compress(s,w);
 for(int i=0;i<64;i++)w[i]=0;for(int i=0;i<8;i++)w[i]=s[i];w[8]=0x80000000;w[15]=256;init(s);compress(s,w);
 for(int i=0;i<8;i++){out[id*32+i*4]=s[i]>>24;out[id*32+i*4+1]=s[i]>>16;out[id*32+i*4+2]=s[i]>>8;out[id*32+i*4+3]=s[i];}
}
'''

def telemetry():
    if sys.platform=='darwin':
        result=subprocess.run([str(metal_executable()),'--telemetry'],capture_output=True,text=True,timeout=3,check=True)
        value=json.loads(result.stdout)
        if value.get('thermal_state') not in (0,1,2,3):raise RuntimeError('Invalid Apple thermal telemetry')
        return value
    executable=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/nvidia-smi.exe'
    result=subprocess.run([str(executable),'--query-gpu=uuid,name,temperature.gpu,power.draw,enforced.power.limit','--format=csv,noheader,nounits'],
        capture_output=True,text=True,timeout=3,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    rows=[row.strip().split(',') for row in result.stdout.strip().splitlines()]
    if len(rows)!=1:raise RuntimeError('GPU mode requires exactly one monitored NVIDIA GPU')
    uuid,name,temp,power,limit=[v.strip() for v in rows[0]]
    temp,power=float(temp),float(power)
    available=limit not in ('[N/A]','N/A','[Not Supported]')
    # Some mobile drivers expose watts but no adjustable power limit. Use
    # conservative 50W-pause / 65W-stop ceilings rather than change the driver.
    limit=float(limit) if available else 65/.85
    if not 0<=temp<=120 or not 0<=power<=1000 or not 20<=limit<=1000:raise RuntimeError('Invalid GPU telemetry')
    return {'uuid':uuid,'name':name,'temperature_c':temp,'power_w':power,'power_limit_w':limit,'power_limit_reported':available}

def thermal_state(sample, paused=False):
    if 'thermal_state' in sample:
        return 'stop' if sample['thermal_state']>=2 else 'pause' if sample['thermal_state']==1 else 'mine'
    hard=sample.get('power_limit_w',65/.85)*.85
    soft=sample.get('power_limit_w',50/.65)*.65
    if sample['temperature_c']>=75 or sample['power_w']>=hard:return 'stop'
    if sample['temperature_c']>=68 or sample['power_w']>=soft:return 'pause'
    if paused and sample['temperature_c']>66:return 'pause'
    return 'mine'

def _worker(pipe):
    try:
        if sys.platform=='darwin':
            return _metal_worker(pipe)
        import pyopencl as cl
        import numpy as np
        devices=[d for p in cl.get_platforms() for d in p.get_devices(device_type=cl.device_type.GPU) if 'NVIDIA' in d.vendor.upper()]
        if len(devices)!=1:raise RuntimeError('Exactly one NVIDIA OpenCL GPU required')
        context=cl.Context(devices);queue=cl.CommandQueue(context)
        program=cl.Program(context,SOURCE).build();kernel=cl.Kernel(program,'hash_headers')
        pipe.send(('ready',devices[0].name))
        while True:
            job=pipe.recv()
            if job is None:break
            prefix,start,count=job
            if len(prefix)!=76 or not 1<=count<=32768 or not 0<=start<=2**32-count:raise ValueError('Unbounded GPU job')
            output=np.empty(count*32,dtype=np.uint8)
            source=cl.Buffer(context,cl.mem_flags.READ_ONLY|cl.mem_flags.COPY_HOST_PTR,hostbuf=prefix)
            dest=cl.Buffer(context,cl.mem_flags.WRITE_ONLY,output.nbytes)
            kernel(queue,(count,),None,source,np.uint32(start),dest)
            cl.enqueue_copy(queue,output,dest).wait();pipe.send(('hashes',output.tobytes()))
    except BaseException as error:
        try:pipe.send(('error',str(error)))
        except (BrokenPipeError,EOFError,OSError):pass
    finally:pipe.close()

def _metal_worker(pipe):
    process=subprocess.Popen([str(metal_executable())],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
    try:
        ready=json.loads(process.stdout.readline())
        if not ready.get('ready'):raise RuntimeError('Metal device initialization failed')
        pipe.send(('ready',ready['name']))
        while True:
            job=pipe.recv()
            if job is None:break
            prefix,start,count=job
            if len(prefix)!=76 or not 1<=count<=32768 or not 0<=start<=2**32-count:raise ValueError('Unbounded Metal job')
            process.stdin.write(json.dumps({'prefix':prefix.hex(),'start':start,'count':count})+'\n');process.stdin.flush()
            result=json.loads(process.stdout.readline())
            if 'error' in result:raise RuntimeError(result['error'])
            pipe.send(('hashes',bytes.fromhex(result['hashes'])))
    finally:
        if process.poll() is None:process.terminate()
        process.wait(timeout=2)

class GPUWorker:
    def __init__(self, stop_file, state_file=None):
        self.stop_file=Path(stop_file);self.state_file=Path(state_file) if state_file else self.stop_file.with_name('gpu-status.json')
        self.process=None;self.paused=False;self.last_sample=None;self.checked=0
        self.latch=self.stop_file.with_name('GPU-SAFETY-STOP')
        if self.latch.exists():raise RuntimeError('GPU safety stop is latched. Check cooling before removing GPU-SAFETY-STOP to retry.')
        self.sample(force=True)
        context=mp.get_context('spawn');self.pipe,child=context.Pipe()
        self.process=context.Process(target=_worker,args=(child,),daemon=True);self.process.start();child.close()
        try:
            kind,value=self.receive(30)
            if kind!='ready':raise RuntimeError(value)
            self.device=value
            # Every startup checks the actual device against CPU SHA256d.
            prefix=bytes(range(76));raw=self.hashes(prefix,0,64)
            for nonce in range(64):
                data=prefix+struct.pack('<I',nonce)
                if raw[nonce*32:nonce*32+32]!=hashlib.sha256(hashlib.sha256(data).digest()).digest():raise RuntimeError('GPU SHA256d self-check failed')
        except BaseException:self.close();raise

    def receive(self, timeout):
        if not self.pipe.poll(timeout):
            self.latch.write_text('GPU worker timeout. Inspect cooling and driver before retrying.\n')
            self.close();raise RuntimeError('GPU worker timed out; stopped without restarting the driver')
        try:kind,value=self.pipe.recv()
        except (EOFError,OSError) as error:
            self.latch.write_text('GPU worker exited unexpectedly.\n');self.close();raise RuntimeError('GPU worker disconnected') from error
        if kind=='error':
            self.latch.write_text(value+'\n');self.close();raise RuntimeError(value)
        return kind,value

    def sample(self,force=False):
        if not force and time.monotonic()-self.checked<1:return
        try:
            value=telemetry();decision=thermal_state(value,self.paused)
            self.last_sample=value;self.paused=decision=='pause';self.checked=time.monotonic()
            state={**value,'phase':decision,'updated_at':time.time(),'duty_cycle_max':0.10,'hard_stop_c':75,'pause_c':68,'resume_c':66}
            self.state_file.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.state_file.with_suffix('.tmp');temporary.write_text(json.dumps(state,indent=2));temporary.replace(self.state_file)
            if decision=='stop':raise RuntimeError('GPU safety threshold reached; manually restart after checking cooling')
        except BaseException as error:
            if hasattr(self,'latch'):self.latch.write_text(str(error)+'\n')
            if hasattr(self,'state_file'):
                self.state_file.write_text(json.dumps({'phase':'safety_stopped','updated_at':time.time(),'error':str(error),**(self.last_sample or {})}))
            self.close();raise

    def hashes(self,prefix,start,count):
        began=time.monotonic();self.pipe.send((prefix,start,count));kind,raw=self.receive(3)
        if kind!='hashes' or len(raw)!=count*32:raise RuntimeError('Invalid GPU response')
        # At most 10% hashing duty cycle. Interruptible idle also gives the
        # OS graphics workload priority without changing global GPU settings.
        end=time.monotonic()+max(0.05,(time.monotonic()-began)*9)
        while time.monotonic()<end and not self.stop_file.exists():time.sleep(min(.05,end-time.monotonic()))
        return raw

    def search(self,prefix,target,seconds=1):
        deadline=time.monotonic()+seconds;start=0
        while time.monotonic()<deadline and not self.stop_file.exists():
            self.sample()
            if self.paused:time.sleep(.2);continue
            count=32768
            raw=self.hashes(prefix,start,count)
            for offset in range(count):
                if int.from_bytes(raw[offset*32:offset*32+32],'little')<=target:
                    nonce=start+offset;header=prefix+struct.pack('<I',nonce)
                    if int.from_bytes(hashlib.sha256(hashlib.sha256(header).digest()).digest(),'little')>target:raise RuntimeError('GPU result failed CPU validation')
                    return nonce
            start+=count
        return None

    def close(self):
        if self.process:
            if self.process.is_alive():self.process.terminate()
            self.process.join(timeout=2);self.process=None

    def __del__(self):self.close()
