"""Reopen a genesis-only main database six hours before launch, with a private mock clock."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core_miner import RPC
from core_runtime import MAIN_GENESIS,LAUNCH_EPOCH,file_hash

def verify(binary,report):
    root=report.parent.parent/'runtime-core-checks';root.mkdir(parents=True,exist_ok=True)
    data=Path(tempfile.mkdtemp(prefix='prelaunch-genesis-restart-',dir=root))
    for cycle in range(2):
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
        with (data/f'cycle-{cycle}.log').open('wb') as log:
            process=subprocess.Popen([str(binary),'-chain=main',f'-datadir={data}',
                f'-mocktime={LAUNCH_EPOCH-6*3600}','-server=1','-rpcbind=127.0.0.1',f'-rpcport={port}',
                '-listen=0','-listenonion=0','-connect=0','-dnsseed=0','-fixedseeds=0','-discover=0',
                '-natpmp=0','-disablewallet=1','-dbcache=32','-maxmempool=16','-par=1'],
                stdout=log,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            rpc=RPC(f'http://127.0.0.1:{port}',data/'.cookie')
            try:
                deadline=time.monotonic()+90
                while time.monotonic()<deadline:
                    if process.poll() is not None:raise RuntimeError(f'Cycle {cycle} stopped; see {data}')
                    try:
                        if rpc('getblockchaininfo')['chain']=='main':break
                    except (OSError,RuntimeError):pass
                    time.sleep(.1)
                else:raise TimeoutError('Genesis restart node did not initialize')
                assert rpc('getblockcount')==0
                assert rpc('getblockhash',0)==MAIN_GENESIS
            finally:
                if process.poll() is None:
                    rpc('stop');process.wait(timeout=60)
    result={'passed':True,'scope':'main_genesis_only_restart_before_scheduled_launch',
        'binary_sha256':file_hash(binary),'genesis':MAIN_GENESIS,'height':0,
        'startup_cycles':2,'mock_time':LAUNCH_EPOCH-6*3600,'machine_clock_changed':False,
        'data_preserved':True,'public_network_joined':False,'blocks_mined':0}
    report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--binary',required=True,type=Path)
    parser.add_argument('--report',required=True,type=Path);args=parser.parse_args()
    verify(args.binary.resolve(),args.report.resolve())
