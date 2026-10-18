"""Private disposable simulation of main consensus; never joins the public chain.

Both nodes bind loopback only, have no discovery, and use a future mock clock.
Generated fixture blocks and wallets must never be reused by the public node.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core_runtime import MAIN_GENESIS,LAUNCH_EPOCH,free_port,file_hash
from core_miner import RPC,APPROVED_LIMIT,RewardLedger

ROOT=Path(__file__).resolve().parents[1]
def until(check,timeout=90):
    deadline=time.monotonic()+timeout
    last=None
    while time.monotonic()<deadline:
        try:
            result=check()
            if result:return result
        except (OSError,RuntimeError) as error:last=str(error)
        time.sleep(.25)
    raise TimeoutError('Fixture check timed out: '+str(last))

def verify(binary):
    (ROOT/'runtime-core-checks').mkdir(exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix='MAIN-PARAMETERS-PRIVATE-FIXTURE-',dir=ROOT/'runtime-core-checks'))
    nodes=[];logs=[];miner=None;stop=root/'STOP'
    try:
        for index in range(2):
            data=root/str(index);data.mkdir();rpcport,peerport=free_port(),free_port()
            log=(data/'process.log').open('wb');logs.append(log)
            process=subprocess.Popen([str(binary),'-chain=main',f'-datadir={data}','-server=1',
                '-listen=1','-bind=127.0.0.1',f'-port={peerport}',f'-rpcport={rpcport}',
                '-rpcbind=127.0.0.1','-connect=0','-dnsseed=0','-fixedseeds=0','-discover=0',
                '-listenonion=0','-natpmp=0','-maxconnections=16','-maxmempool=32','-dbcache=32',
                '-par=1',f'-mocktime={LAUNCH_EPOCH+86400}'],stdout=log,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW)
            rpc=RPC(f'http://127.0.0.1:{rpcport}',data/'.cookie')
            nodes.append((process,rpc,peerport));until(lambda:rpc('getblockchaininfo'))
            assert rpc('getblockhash',0)==MAIN_GENESIS
        a,b=nodes[0][1],nodes[1][1]
        a('addnode',f'127.0.0.1:{nodes[1][2]}','onetry')
        until(lambda:a('getconnectioncount') and b('getconnectioncount'))
        a('createwallet','PRIVATE-FIXTURE-NEVER-USE-PUBLICLY')
        wallet=RPC(a.url+'/wallet/PRIVATE-FIXTURE-NEVER-USE-PUBLICLY',a.cookie)
        address=wallet('getnewaddress');script=wallet('getaddressinfo',address)['scriptPubKey']
        template=wallet('getblocktemplate',{'rules':['segwit']})
        assert template['height']==1 and template['coinbasevalue']==40*100_000_000
        assert template.get('default_witness_commitment')
        config={'armed':True,'network':'pawquanta-main-v1','genesis':MAIN_GENESIS,
            'rpc_url':wallet.url,'cookie_file':str(wallet.cookie),'receiving_address':address,
            'ledger_file':str(root/'fixture-rewards.sqlite'),'limit_atomic_units':APPROVED_LIMIT,
            'not_before_utc_epoch':0}
        (root/'fixture-only-miner.json').write_text(json.dumps(config))
        log=(root/'miner.log').open('wb');logs.append(log)
        miner=subprocess.Popen([sys.executable,str(ROOT/'core_miner.py'),'--config',str(root/'fixture-only-miner.json'),
            '--stop-file',str(stop)],stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        until(lambda:a('getblockcount')>=3,timeout=900)
        stop.touch();assert miner.wait(timeout=20)==0
        until(lambda:a('getbestblockhash')==b('getbestblockhash'))
        ledger=RewardLedger(root/'fixture-rewards.sqlite',MAIN_GENESIS,script)
        earned=ledger.sync(a)[1];assert earned==a('getblockcount')*40*100_000_000
        ledger.db.close()
        result={'passed':True,'scope':'loopback_main_parameter_simulation_future_mock_clock',
            'binary_sha256':file_hash(binary),'height':a('getblockcount'),'genesis':MAIN_GENESIS,
            'separate_nodes_and_miner':True,'own_main_consensus_blocks_accepted':True,
            'segwit_coinbase_accepted':True,'public_mainnet_launched':False,
            'real_owner_wallet_used':False,'fixture_coins_have_no_public_validity_now':True,
            'fixture_directory':str(root)}
        (ROOT/'reports/main-parameter-simulation.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
    finally:
        stop.touch()
        if miner and miner.poll() is None:
            try:miner.wait(timeout=30)
            except subprocess.TimeoutExpired:print('Fixture miner is still stopping; its files were preserved')
        for process,rpc,_ in nodes:
            if process.poll() is None:
                try:rpc('stop');process.wait(timeout=60)
                except (OSError,RuntimeError,subprocess.TimeoutExpired):print('Fixture node is still stopping; no forced disk termination')
        for log in logs:log.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--binary',required=True,type=Path)
    verify(parser.parse_args().binary.resolve())
