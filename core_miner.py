"""Local, single-worker Bitcoin-Core-protocol miner and durable reward accounting.

RPC remains on loopback. No network is armed by importing or running --help.
The public-network identity must be supplied by a verified deployment manifest.
"""
import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

UNIT = 100_000_000
APPROVED_LIMIT = 1_260_000 * UNIT


def sha256d(data):
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def compact_size(n):
    if not 0 <= n <= 0xffffffffffffffff:
        raise ValueError('CompactSize out of range')
    if n < 253:
        return bytes([n])
    return bytes([253 if n <= 0xffff else 254 if n <= 0xffffffff else 255]) + struct.pack(
        '<H' if n <= 0xffff else '<I' if n <= 0xffffffff else '<Q', n)


def height_script(height):
    if height < 1:
        raise ValueError('Only post-genesis blocks can be mined')
    if height <= 16:
        return bytes([0x50 + height])
    raw = height.to_bytes((height.bit_length() + 7) // 8, 'little')
    if raw[-1] & 0x80:
        raw += b'\0'
    return bytes([len(raw)]) + raw


def target_from_bits(bits):
    number = int(bits, 16)
    size, word = number >> 24, number & 0x7fffff
    if number & 0x800000 or not word:
        raise ValueError('Negative or zero work target')
    target = word >> (8 * (3 - size)) if size <= 3 else word << (8 * (size - 3))
    if not 0 < target < 2**256:
        raise ValueError('Work target overflows 256 bits')
    return target


def merkle_root(txids):
    if not txids:
        raise ValueError('Empty block')
    level = list(txids)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [sha256d(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def candidate(template, payout_script, reward, extra_nonce=None):
    """Return the 76-byte header prefix and block body, including SegWit commitment."""
    if type(reward) is not int or not 0 < reward <= template['coinbasevalue']:
        raise ValueError('Reward exceeds the template or is not an atomic-unit integer')
    extra_nonce = os.urandom(12) if extra_nonce is None else extra_nonce
    script = height_script(template['height']) + bytes([len(extra_nonce)]) + extra_nonce
    if not 2 <= len(script) <= 100 or len(extra_nonce) > 75:
        raise ValueError('Invalid coinbase script length')
    vin = b'\x01' + b'\0' * 32 + b'\xff' * 4 + compact_size(len(script)) + script + b'\xff' * 4
    outputs = [(reward, bytes.fromhex(payout_script))]
    commitment = template.get('default_witness_commitment')
    if commitment:
        outputs.append((0, bytes.fromhex(commitment)))
    vout = compact_size(len(outputs)) + b''.join(
        struct.pack('<Q', value) + compact_size(len(script_pubkey)) + script_pubkey
        for value, script_pubkey in outputs)
    version, locktime = struct.pack('<I', 2), b'\0' * 4
    base_tx = version + vin + vout + locktime
    coinbase = version + b'\x00\x01' + vin + vout + b'\x01\x20' + b'\0' * 32 + locktime if commitment else base_tx
    transactions = template['transactions']
    root = merkle_root([sha256d(base_tx)] + [bytes.fromhex(tx['txid'])[::-1] for tx in transactions])
    header = struct.pack('<I', template['version'] & 0xffffffff)
    header += bytes.fromhex(template['previousblockhash'])[::-1] + root
    header += struct.pack('<II', template['curtime'], int(template['bits'], 16))
    body = compact_size(1 + len(transactions)) + coinbase + b''.join(bytes.fromhex(tx['data']) for tx in transactions)
    return header, body


class RPC:
    def __init__(self, url, cookie):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', '::1', 'localhost') or parsed.username:
            raise ValueError('Wallet RPC must use local loopback without URL credentials')
        self.url, self.cookie = url, Path(cookie)
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, request, file, code, message, headers, new_url):
                return None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())

    def __call__(self, method, *params):
        credential = self.cookie.read_bytes().strip()
        if not credential or len(credential) > 1024:
            raise ValueError('Invalid local RPC cookie')
        request = urllib.request.Request(self.url, json.dumps({'jsonrpc': '2.0', 'id': 1,
            'method': method, 'params': params}).encode(), headers={
                'Authorization': 'Basic ' + base64.b64encode(credential).decode(),
                'Content-Type': 'application/json'})
        try:
            response = self.opener.open(request, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read(32 * 1024 * 1024 + 1)
        if len(raw) > 32 * 1024 * 1024:
            raise ValueError('Oversize RPC response')
        result = json.loads(raw, parse_float=Decimal)
        if result.get('error'):
            raise RuntimeError(f"RPC {method}: {result['error']['message']}")
        return result['result']


class RewardLedger:
    """Only canonical coinbase outputs to the pinned payout script count.

    Unspent balance is deliberately not used: spending never resets earnings.
    A persisted block-hash journal allows reorg rollback and restart recovery.
    """
    def __init__(self, filename, genesis, payout_script):
        self.db = sqlite3.connect(filename, timeout=10)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS identity (genesis TEXT, script TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS rewards (height INTEGER PRIMARY KEY, hash TEXT NOT NULL, units INTEGER NOT NULL)')
        identity = self.db.execute('SELECT genesis, script FROM identity').fetchone()
        if identity is None:
            self.db.execute('INSERT INTO identity VALUES (?, ?)', (genesis, payout_script))
            self.db.commit()
        elif identity != (genesis, payout_script):
            self.db.close()
            raise ValueError('Ledger belongs to a different genesis or payout script')
        self.script, self.genesis = payout_script, genesis

    def sync(self, rpc):
        if rpc('getblockhash', 0) != self.genesis:
            raise ValueError('Node changed networks while miner was running')
        # Pin both ends of this scan; retry if the node reorganizes during RPC reads.
        for attempt in range(5):
            tip = rpc('getbestblockhash')
            height = rpc('getblockcount')
            if rpc('getblockhash', height) != tip:
                continue
            with self.db:
                while True:
                    last = self.db.execute('SELECT height, hash FROM rewards ORDER BY height DESC LIMIT 1').fetchone()
                    if last is None or (last[0] <= height and rpc('getblockhash', last[0]) == last[1]):
                        break
                    self.db.execute('DELETE FROM rewards WHERE height=?', (last[0],))
                start = 1 if last is None else last[0] + 1
                for current in range(start, height + 1):
                    block_hash = rpc('getblockhash', current)
                    block = rpc('getblock', block_hash, 2)
                    tx = block['tx'][0]
                    if block.get('height') != current or 'coinbase' not in tx['vin'][0]:
                        raise ValueError('Invalid coinbase response')
                    units = 0
                    for output in tx['vout']:
                        if output['scriptPubKey']['hex'] == self.script:
                            amount = Decimal(str(output['value'])) * UNIT
                            if amount != amount.to_integral_value() or amount < 0:
                                raise ValueError('Invalid reward precision')
                            units += int(amount)
                    self.db.execute('INSERT INTO rewards VALUES (?, ?, ?)', (current, block_hash, units))
            if rpc('getbestblockhash') == tip:
                earned = self.db.execute('SELECT COALESCE(SUM(units),0) FROM rewards').fetchone()[0]
                return tip, earned
        raise RuntimeError('Chain changed repeatedly while checking mining quota')


@contextmanager
def exclusive_miner(ledger_file):
    """Refuse a second local miner using the same quota journal."""
    with open(str(ledger_file) + '.miner-lock', 'a+b') as handle:
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            if not handle.read(1):
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def mine(config, stop_file, development=False):
    with exclusive_miner(config['ledger_file']):
        _mine(config, stop_file, development)


def _mine(config, stop_file, development=False):
    if config.get('armed') is not True:
        raise ValueError('Miner is not armed')
    if config['limit_atomic_units'] != APPROVED_LIMIT:
        raise ValueError('Mining cap differs from the approved 1,260,000 PQUA')
    rpc = RPC(config['rpc_url'], config['cookie_file'])
    info = rpc('getblockchaininfo')
    expected_chain = 'regtest' if development else 'main'
    if info['chain'] != expected_chain or rpc('getblockhash', 0) != config['genesis']:
        raise ValueError('Pinned network identity does not match the live node')
    if not development and config.get('network') != 'pawquanta-main-v1':
        raise ValueError('Public Pawquanta identity is not configured')
    payout = rpc('getaddressinfo', config['receiving_address'])
    if not payout.get('ismine') or payout.get('iswatchonly'):
        raise ValueError('Receiving wallet does not own this payout address')
    script = payout['scriptPubKey']
    ledger = RewardLedger(config['ledger_file'], config['genesis'], script)
    print('Miner configured: one CPU worker; cap includes immature rewards and fees.', flush=True)
    while not stop_file.exists():
        if time.time() < config['not_before_utc_epoch']:
            time.sleep(min(1, config['not_before_utc_epoch'] - time.time()))
            continue
        tip, earned = ledger.sync(rpc)
        if earned >= APPROVED_LIMIT:
            print('Mining cap reached. Stopped.', flush=True)
            return
        template = rpc('getblocktemplate', {'rules': ['segwit']})
        if template['previousblockhash'] != tip:
            continue
        reward = min(template['coinbasevalue'], APPROVED_LIMIT - earned)
        header, body = candidate(template, script, reward)
        target = target_from_bits(template['bits'])
        if target != int(template['target'], 16):
            raise ValueError('Template target and bits disagree')
        deadline = time.monotonic() + 1
        for nonce in range(2**32):
            raw_header = header + struct.pack('<I', nonce)
            if int.from_bytes(sha256d(raw_header), 'little') <= target:
                # Recheck the canonical quota immediately before submission.
                current_tip, current_earned = ledger.sync(rpc)
                if current_tip != tip or current_earned + reward > APPROVED_LIMIT:
                    break
                result = rpc('submitblock', (raw_header + body).hex())
                print('Block accepted' if result is None else f'Block rejected: {result}', flush=True)
                break
            if nonce % 4096 == 0 and (time.monotonic() >= deadline or stop_file.exists()):
                break
        # Brief yield keeps this bounded single worker responsive on the MSI.
        time.sleep(0.02)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--stop-file', required=True, type=Path)
    parser.add_argument('--development-regtest', action='store_true')
    arguments = parser.parse_args()
    mine(json.loads(arguments.config.read_text()), arguments.stop_file, arguments.development_regtest)
