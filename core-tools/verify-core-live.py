"""Two real node processes, separate miner, relay/payment/reorg and quota checks.

Regression network only. Data stays in a newly created dedicated directory.
Never starts a Bitcoin/Pawquanta public-network daemon.
"""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core_miner as m


def available_port():
    with socket.socket() as stream:
        stream.bind(('127.0.0.1', 0))
        return stream.getsockname()[1]


def until(check, timeout=45):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except (OSError, RuntimeError, KeyError) as error:
            last_error = str(error)
        time.sleep(0.1)
    raise TimeoutError(f'Live check did not pass: {last_error}')


def verify(binary, report):
    report.parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='pqua-live-', dir=report.parent))
    nodes, logs = [], []
    miner = None
    try:
        for index in range(2):
            data = root / f'node-{index}'
            data.mkdir()
            rpc_port, peer_port = available_port(), available_port()
            log = (data / 'process.log').open('wb')
            logs.append(log)
            process = subprocess.Popen([str(binary), '-regtest', f'-datadir={data}',
                '-server=1', '-listen=1', '-bind=127.0.0.1', f'-port={peer_port}',
                f'-rpcport={rpc_port}', '-rpcbind=127.0.0.1', '-dnsseed=0',
                '-fixedseeds=0', '-discover=0', '-listenonion=0', '-connect=0',
                '-dbcache=32', '-par=2', '-maxconnections=8', '-fallbackfee=0.00001'],
                stdout=log, stderr=subprocess.STDOUT)
            rpc = m.RPC(f'http://127.0.0.1:{rpc_port}', data / 'regtest/.cookie')
            nodes.append((process, rpc, data, peer_port))
            until(lambda: process.poll() is None and rpc('getblockchaininfo'))
        a, b = nodes[0][1], nodes[1][1]
        a('addnode', f'127.0.0.1:{nodes[1][3]}', 'onetry')
        until(lambda: a('getconnectioncount') >= 1 and b('getconnectioncount') >= 1)
        a('createwallet', 'miner')
        b('createwallet', 'recipient')
        wa = m.RPC(a.url + '/wallet/miner', a.cookie)
        wb = m.RPC(b.url + '/wallet/recipient', b.cookie)
        address = wa('getnewaddress', 'test-mining')
        receiving = wb('getnewaddress', 'test-receiving')
        genesis = a('getblockhash', 0)
        script = wa('getaddressinfo', address)['scriptPubKey']
        # Test the exact byte serialization against the real consensus implementation.
        template = wa('getblocktemplate', {'rules': ['segwit']})
        # A one-atomic-unit reward exercises the final capped block without overshoot.
        header, body = m.candidate(template, script, 1)
        target = m.target_from_bits(template['bits'])
        for nonce in range(10000):
            raw = header + nonce.to_bytes(4, 'little')
            if int.from_bytes(m.sha256d(raw), 'little') <= target:
                assert a('submitblock', (raw + body).hex()) is None
                break
        else:
            raise AssertionError('Regression proof of work not found')
        until(lambda: b('getbestblockhash') == a('getbestblockhash'))
        # Separate miner executable/process joins via authenticated local RPC.
        config = {'armed': True, 'network': 'development-regtest', 'genesis': genesis,
            'rpc_url': wa.url, 'cookie_file': str(wa.cookie), 'receiving_address': address,
            'ledger_file': str(root / 'quota.sqlite'), 'limit_atomic_units': m.APPROVED_LIMIT,
            'not_before_utc_epoch': 0}
        config_file, stop = root / 'miner.json', root / 'STOP'
        config_file.write_text(json.dumps(config))
        miner_log = (root / 'miner.log').open('wb')
        logs.append(miner_log)
        miner = subprocess.Popen([sys.executable, str(Path(m.__file__)), '--config', str(config_file),
            '--stop-file', str(stop), '--development-regtest'], stdout=miner_log, stderr=subprocess.STDOUT)
        until(lambda: a('getblockcount') >= 6)
        stop.touch()
        assert miner.wait(timeout=15) == 0
        until(lambda: b('getbestblockhash') == a('getbestblockhash'))
        # Mature outputs, send a signed payment, verify mempool relay and confirmation.
        wa('generatetoaddress', 101, address)
        until(lambda: b('getbestblockhash') == a('getbestblockhash'))
        ledger = m.RewardLedger(root / 'quota.sqlite', genesis, script)
        before = ledger.sync(a)[1]
        transaction = wa('sendtoaddress', receiving, 10)
        until(lambda: transaction in b('getrawmempool'))
        wa('generatetoaddress', 1, address)
        until(lambda: wb('gettransaction', transaction)['confirmations'] >= 1)
        after = ledger.sync(a)[1]
        assert after > before, 'Spending must not reset cumulative mining earnings'
        # A competing branch removes a reward. The persisted ledger must follow the winning chain.
        old_tip = a('getbestblockhash')
        a('invalidateblock', old_tip)
        reward_without_tip = ledger.sync(a)[1]
        assert reward_without_tip < after
        wa('generatetoaddress', 2, address)
        a('reconsiderblock', old_tip)
        until(lambda: b('getbestblockhash') == a('getbestblockhash'))
        result = {'passed': True, 'scope': 'two_real_local_regression_nodes_and_separate_miner',
            'public_reachability_verified': False, 'mainnet_launched': False,
            'height': a('getblockcount'), 'tip': a('getbestblockhash'),
            'custom_coinbase_accepted': True, 'separate_miner_process': True,
            'one_atomic_unit_final_reward_accepted': True,
            'payment_relay_and_confirmation': True, 'reorg_reward_accounting': True,
            'spending_does_not_reset_quota': True, 'data_directory': str(root)}
        ledger.db.close()
        report.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
    finally:
        if miner is not None and miner.poll() is None:
            (root / 'STOP').touch()
            try:
                miner.wait(timeout=15)
            except subprocess.TimeoutExpired:
                miner.terminate()
                miner.wait(timeout=10)
        for process, rpc, data, peer_port in nodes:
            if process.poll() is None:
                try:
                    rpc('stop')
                    process.wait(timeout=20)
                except (OSError, RuntimeError, subprocess.TimeoutExpired):
                    process.terminate()
                    process.wait(timeout=10)
        for log in logs:
            log.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    verify(args.binary.resolve(), args.report.resolve())
