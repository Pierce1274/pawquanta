"""Pawquanta private research testnet. No real funds. Python 3.11+."""
import argparse
import base64
import copy
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import threading
import time
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
import sys
sys.path.insert(0, str(Path(__file__).parent / 'Pawquanta-research'))
from chonk_hash import digest

NETWORK = 'pawquanta-private-v1'
UNIT = 100_000_000
HALVING = 525_000
CAP = 42_000_000 * UNIT
INITIAL_TARGET = (1 << 256) // 16
MAX_TARGET = (1 << 256) // 2
INTERVAL = 120
BLOCK_SECONDS = 60
MATURITY = 3
MAX_BYTES = 65_536
MAX_CHAIN = 2000  # Deliberate bounded research network lifetime.
MAX_TX = 32
GENESIS = {'network': NETWORK, 'height': 0, 'previous': '0'*64,
           'timestamp': 0, 'target': INITIAL_TARGET, 'nonce': 0,
           'miner': 'GENESIS', 'transactions': []}
ADDRESS = re.compile(r'pqua_[0-9a-f]{40}\Z')

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')

def strict_load(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))

def sha(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()

def integer(value, low=0, high=(1 << 63)-1):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('integer out of range')
    return value

def address(public):
    return 'pqua_' + hashlib.sha256(public).hexdigest()[:40]

def valid_address(value):
    if not isinstance(value, str) or not ADDRESS.fullmatch(value):
        raise ValueError('invalid PQUA address')
    return value

def subsidy(height):
    integer(height, 1)
    return (40 * UNIT) >> ((height-1)//HALVING)

def emission_total():
    return HALVING * sum((40*UNIT) >> i for i in range((40*UNIT).bit_length()))

def pow_bytes(block):
    # Fixed-size commitment prevents transactions exceeding CHONK's 4096-byte header limit.
    header = hashlib.sha256(canonical({k:v for k,v in block.items() if k != 'nonce'})).digest()
    return digest(b'PQUA-POW-v1\0' + header, block['nonce'], 16, 32)

def work(block):
    return (1 << 256) // (block['target']+1)

def next_target(chain):
    height = len(chain)
    old = chain[-1]['target']
    if height <= INTERVAL or (height-1) % INTERVAL:
        return old
    elapsed = chain[-1]['timestamp'] - chain[-INTERVAL]['timestamp']
    expected = (INTERVAL-1) * BLOCK_SECONDS
    elapsed = max(expected//4, min(expected*4, elapsed))
    return max(1, min(MAX_TARGET, old*elapsed//expected))

def tx_unsigned(tx):
    return {k:v for k,v in tx.items() if k != 'signature'}

def verify_tx(tx):
    try:
        if type(tx) is not dict or set(tx) != {'network','from','to','amount','fee','nonce','public_key','signature'}:
            return False
        if tx['network'] != NETWORK:
            return False
        valid_address(tx['from']); valid_address(tx['to'])
        integer(tx['amount'], 1, CAP); integer(tx['fee'], 0, CAP); integer(tx['nonce'])
        pub = base64.b64decode(tx['public_key'], validate=True)
        sig = base64.b64decode(tx['signature'], validate=True)
        if len(pub) != 32 or len(sig) != 64 or tx['from'] != address(pub):
            return False
        Ed25519PublicKey.from_public_bytes(pub).verify(sig, b'PQUA-TX-v1\0' + canonical(tx_unsigned(tx)))
        return True
    except (ValueError, TypeError, KeyError, InvalidSignature):
        return False

def sign(key, to, amount, nonce, fee=0):
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    tx = {'network':NETWORK, 'from':address(pub), 'to':to, 'amount':amount,
          'fee':fee, 'nonce':nonce, 'public_key':base64.b64encode(pub).decode()}
    tx['signature'] = base64.b64encode(key.sign(b'PQUA-TX-v1\0'+canonical(tx))).decode()
    if not verify_tx(tx):
        raise ValueError('invalid payment')
    return tx

def apply_tx(tx, balances, nonces):
    if not verify_tx(tx):
        raise ValueError('invalid signed transaction')
    src = tx['from']; cost = tx['amount']+tx['fee']
    if tx['nonce'] != nonces.get(src, 0) or balances.get(src, 0) < cost:
        raise ValueError('nonce or available balance')
    balances[src] -= cost
    balances[tx['to']] = balances.get(tx['to'], 0)+tx['amount']
    nonces[src] = tx['nonce']+1

def validate(chain, now=None):
    if type(chain) is not list or not 1 <= len(chain) <= MAX_CHAIN or canonical(chain[0]) != canonical(GENESIS):
        raise ValueError('genesis or chain length')
    if len(canonical(chain)) > 8*1024*1024:
        raise ValueError('research chain byte limit')
    now = int(time.time()) if now is None else now
    balances, nonces, pending = {}, {}, []
    total_work = 0
    for height, block in enumerate(chain[1:], 1):
        if type(block) is not dict or set(block) != set(GENESIS) or len(canonical(block)) > MAX_BYTES:
            raise ValueError('block schema or size')
        integer(block['height'], height, height); integer(block['nonce'], 0, (1<<64)-1)
        integer(block['timestamp']); integer(block['target'], 1, MAX_TARGET)
        valid_address(block['miner'])
        prefix = chain[:height]
        median = int(statistics.median([b['timestamp'] for b in prefix[-11:]]))
        if block['network'] != NETWORK or block['previous'] != sha(prefix[-1]):
            raise ValueError('network or parent')
        if not median < block['timestamp'] <= now+120:
            raise ValueError('timestamp')
        if block['target'] != next_target(prefix) or int.from_bytes(pow_bytes(block), 'big') > block['target']:
            raise ValueError('target or proof')
        if type(block['transactions']) is not list or len(block['transactions']) > MAX_TX:
            raise ValueError('transaction count')
        for unlock, miner, amount in pending[:]:
            if unlock <= height:
                balances[miner] = balances.get(miner, 0)+amount
                pending.remove((unlock, miner, amount))
        fees = 0
        for tx in block['transactions']:
            apply_tx(tx, balances, nonces); fees += tx['fee']
        pending.append((height+MATURITY, block['miner'], subsidy(height)+fees))
        total_work += work(block)
    return {'balances':balances, 'nonces':nonces, 'pending':pending, 'work':total_work}

def mine(chain, miner, transactions=None, max_attempts=100000):
    valid_address(miner)
    block = {'network':NETWORK, 'height':len(chain), 'previous':sha(chain[-1]),
             'timestamp':max(int(time.time()), chain[-1]['timestamp']+1),
             'target':next_target(chain), 'nonce':0, 'miner':miner, 'transactions':transactions or []}
    for nonce in range(max_attempts):
        block['nonce'] = nonce
        if int.from_bytes(pow_bytes(block),'big') <= block['target']:
            validate(chain+[block]); return block
    raise ValueError('mining attempt budget exhausted')

def atomic_save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix+'.tmp')
    with open(temp, 'wb') as out:
        out.write(canonical(value)); out.flush(); os.fsync(out.fileno())
    os.replace(temp, path)

def new_wallet(path, password):
    if len(password) < 12:
        raise ValueError('use at least 12 password characters')
    key = Ed25519PrivateKey.generate()
    encrypted = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                 serialization.BestAvailableEncryption(password.encode()))
    with open(path, 'xb') as out:
        out.write(encrypted)
    return address(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))

def load_wallet(path, password):
    key = serialization.load_pem_private_key(Path(path).read_bytes(), password.encode())
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('wrong key type')
    return key

def request(url, path, data=None, token=None):
    headers = {'Content-Type':'application/json'}
    if token: headers['X-PQUA-Key'] = token
    req = urllib.request.Request(url+path, data=None if data is None else canonical(data), headers=headers)
    with urllib.request.urlopen(req, timeout=4) as response:
        raw = response.read(8*1024*1024+1)
    if len(raw) > 8*1024*1024:
        raise ValueError('response too large')
    return strict_load(raw)

class Node:
    def __init__(self, path, peers=(), token=''):
        self.path = Path(path); self.lock = threading.RLock()
        self.chain = strict_load(self.path.read_bytes()) if self.path.exists() else [copy.deepcopy(GENESIS)]
        self.state_cache = validate(self.chain)
        self.pool = []; self.peers = tuple(peers); self.token = token; self.peer_status = {}
        self.stopping = threading.Event()

    def status(self):
        with self.lock:
            state = self.state_cache
            return {'network':NETWORK, 'genesis':sha(GENESIS), 'height':len(self.chain)-1,
                    'tip':sha(self.chain[-1]), 'work':state['work'], 'balances':state['balances'],
                    'next_nonces':state['nonces'], 'immature_rewards':state['pending'],
                    'mempool':len(self.pool), 'peers':dict(self.peer_status), 'testnet_only':True}

    def accept_chain(self, candidate):
        new = validate(candidate)
        with self.lock:
            old = self.state_cache
            # Equal work: lexical smaller tip wins, independent of message order.
            if (new['work'], -int(sha(candidate[-1]),16)) <= (old['work'], -int(sha(self.chain[-1]),16)):
                return False
            included = {sha(tx) for b in candidate for tx in b['transactions']}
            detached = [tx for b in self.chain for tx in b['transactions'] if sha(tx) not in included]
            oldpool = self.pool
            atomic_save(self.path, candidate)
            self.chain = copy.deepcopy(candidate); self.state_cache = new; self.pool = []
            for tx in oldpool+detached:
                try: self.add_tx(tx)
                except ValueError: pass
            return True

    def add_tx(self, tx):
        with self.lock:
            if len(self.pool) >= MAX_TX or any(sha(tx)==sha(t) for t in self.pool):
                raise ValueError('pool full or duplicate')
            # Validate against the next height, where maturing coins become spendable.
            state = copy.deepcopy(self.state_cache)
            for unlock, miner, amount in state['pending']:
                if unlock <= len(self.chain):
                    state['balances'][miner] = state['balances'].get(miner,0)+amount
            for existing in self.pool: apply_tx(existing, state['balances'], state['nonces'])
            apply_tx(tx, state['balances'], state['nonces'])
            self.pool.append(copy.deepcopy(tx))

    def sync_once(self):
        for peer in self.peers:
            try:
                hello = request(peer, '/hello', token=self.token)
                if hello != {'network':NETWORK,'genesis':sha(GENESIS),'version':1}:
                    raise ValueError('incompatible peer')
                self.accept_chain(request(peer, '/chain', token=self.token))
                for tx in request(peer, '/mempool', token=self.token):
                    try: self.add_tx(tx)
                    except ValueError: pass
                with self.lock: self.peer_status[peer] = 'connected'
            except Exception as exc:
                with self.lock: self.peer_status[peer] = type(exc).__name__

    def sync_loop(self):
        while not self.stopping.is_set():
            self.sync_once(); self.stopping.wait(2)


DASHBOARD = '''<!doctype html><meta charset="utf-8"><title>Pawquanta private testnet</title>
<style>body{font:17px system-ui;max-width:1000px;margin:40px auto;background:#131821;color:#eee;padding:20px}img{width:130px;border-radius:20px;float:right}pre{white-space:pre-wrap;word-break:break-all;background:#202939;padding:20px}b{color:#ffbc72}</style>
<img src="/mascot.jpg"><h1>Pawquanta · PQUA</h1><b>PRIVATE RESEARCH TESTNET · NO MONETARY VALUE</b>
<p>Standalone experimental chain. 1 PQUA = 100,000,000 atomic units. Rewards mature after 3 blocks.</p>
<h2 id="head">Connecting…</h2><pre id="state"></pre><p>Read-only explorer. Wallet keys stay in your local CLI.</p>
<script>async function refresh(){try{let s=await(await fetch('/status')).json();document.querySelector('#head').textContent='Block '+s.height+' · '+s.mempool+' pending payments';document.querySelector('#state').textContent=JSON.stringify(s,null,2)}catch(e){document.querySelector('#head').textContent='Node offline'}}refresh();setInterval(refresh,3000)</script>'''

class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, addr, node):
        self.node = node; self.slots = threading.BoundedSemaphore(8)
        self.rates = {}; self.rate_lock = threading.Lock()
        super().__init__(addr, Handler)
    def process_request(self, request_socket, client_address):
        if not self.slots.acquire(False):
            self.shutdown_request(request_socket); return
        try: super().process_request(request_socket, client_address)
        except Exception:
            self.slots.release(); raise
    def process_request_thread(self, request_socket, client_address):
        try: super().process_request_thread(request_socket, client_address)
        finally: self.slots.release()

class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup(); self.connection.settimeout(4)
    def log_message(self, *args): pass
    def reply(self, code, value, kind='application/json'):
        raw = canonical(value) if kind == 'application/json' else value
        self.send_response(code); self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(raw))); self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(raw)
    def allowed(self, write=False):
        now = int(time.time())//60; ip = self.client_address[0]
        with self.server.rate_lock:
            self.server.rates = {k:v for k,v in self.server.rates.items() if v[0] == now}
            period, count = self.server.rates.get(ip,(now,0))
            self.server.rates[ip] = (now,count+1)
        if count >= 240:
            self.reply(429, {'error':'rate limit'}); return False
        if write or self.path in ('/chain','/mempool','/hello'):
            import hmac
            if not self.server.node.token or not hmac.compare_digest(self.headers.get('X-PQUA-Key',''),self.server.node.token):
                self.reply(403, {'error':'private testnet key required'}); return False
        return True
    def do_GET(self):
        if not self.allowed(): return
        n = self.server.node
        with n.lock:
            if self.path in ('/countdown','/countdown/'):
                return self.reply(200,(Path(__file__).parent/'countdown.html').read_bytes(),'text/html; charset=utf-8')
            if self.path == '/countdown-status':
                from countdown import status
                return self.reply(200,status(len(n.chain)-1))
            if self.path == '/': return self.reply(200,DASHBOARD.encode(),'text/html; charset=utf-8')
            if self.path == '/mascot.jpg':
                return self.reply(200,(Path(__file__).parent/'Pawquanta-research/assets/mascot.jpg').read_bytes(),'image/jpeg')
            if self.path == '/hello': return self.reply(200,{'network':NETWORK,'genesis':sha(GENESIS),'version':1})
            if self.path == '/status': return self.reply(200,n.status())
            if self.path == '/chain': return self.reply(200,n.chain)
            if self.path == '/mempool': return self.reply(200,n.pool)
        self.reply(404,{'error':'unknown endpoint'})
    def do_POST(self):
        if not self.allowed(True): return
        try:
            if self.headers.get('Transfer-Encoding'): raise ValueError('no chunked requests')
            size = int(self.headers.get('Content-Length','0'))
            limit = 8*1024*1024 if self.path == '/chain' else MAX_BYTES
            if not 0 < size <= limit: raise ValueError('request length')
            raw = self.rfile.read(size)
            if len(raw) != size: raise ValueError('truncated request')
            obj = strict_load(raw)
            n = self.server.node
            if self.path == '/tx': n.add_tx(obj); result = {'accepted':True,'txid':sha(obj)}
            elif self.path == '/block':
                if type(obj) is not dict: raise ValueError('block must be an object')
                with n.lock:
                    if obj.get('previous') != sha(n.chain[-1]): raise ValueError('orphan; sync full chain')
                    result = {'accepted':n.accept_chain(n.chain+[obj])}
            elif self.path == '/chain': result = {'accepted':n.accept_chain(obj)}
            else: return self.reply(404,{'error':'unknown endpoint'})
            self.reply(200,result)
        except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
            self.reply(400,{'error':'invalid message'})

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='cmd',required=True)
    p = subs.add_parser('node'); p.add_argument('--port',type=int,default=18701); p.add_argument('--bind',default='127.0.0.1'); p.add_argument('--data',required=True); p.add_argument('--peer',action='append',default=[])
    p = subs.add_parser('wallet'); p.add_argument('file')
    p = subs.add_parser('address'); p.add_argument('file')
    for cmd in ('status','mine','send'):
        p = subs.add_parser(cmd); p.add_argument('--url',default='http://127.0.0.1:18701')
        if cmd == 'mine':
            p.add_argument('--address',required=True); p.add_argument('--blocks',type=int,default=1); p.add_argument('--interval',type=float,default=1)
        if cmd == 'send':
            p.add_argument('--wallet',required=True); p.add_argument('--to',required=True); p.add_argument('--amount',type=int,required=True,help='atomic units'); p.add_argument('--fee',type=int,default=0)
    args = parser.parse_args(); token = os.environ.get('PQUA_TESTNET_KEY','')
    if args.cmd == 'wallet':
        pw = getpass.getpass('New wallet password (12+ characters): ')
        if pw != getpass.getpass('Confirm password: '): raise ValueError('password mismatch')
        print(new_wallet(args.file,pw)); return
    if args.cmd == 'address':
        key = load_wallet(args.file,getpass.getpass('Wallet password: '))
        print(address(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw))); return
    if args.cmd == 'node':
        if len(token) < 24: raise ValueError('set PQUA_TESTNET_KEY to a random shared secret of 24+ characters')
        if len(args.peer)>8: raise ValueError('maximum 8 static peers')
        node = Node(args.data,args.peer,token); server = Server((args.bind,args.port),node)
        threading.Thread(target=node.sync_loop,daemon=True).start()
        print(f'{NETWORK} http://{args.bind}:{args.port}',flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally: node.stopping.set(); server.server_close()
        return
    if args.cmd == 'status': print(json.dumps(request(args.url,'/status'),indent=2)); return
    if args.cmd == 'send':
        key = load_wallet(args.wallet,getpass.getpass('Wallet password: '))
        src = address(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw))
        status = request(args.url,'/status')
        # One outstanding CLI payment per sender: use the pool to determine its next nonce.
        pool = request(args.url,'/mempool',token=token)
        nonce = status['next_nonces'].get(src,0)+sum(tx['from']==src for tx in pool)
        tx = sign(key,args.to,args.amount,nonce,args.fee)
        print(request(args.url,'/tx',tx,token)); return
    if not 1 <= args.blocks <= 100 or args.interval < 0.25: raise ValueError('1..100 blocks and interval >= .25 seconds')
    for _ in range(args.blocks):
        chain = request(args.url,'/chain',token=token)
        pool = request(args.url,'/mempool',token=token)
        block = mine(chain,args.address,pool)
        print(request(args.url,'/block',block,token),flush=True)
        time.sleep(args.interval)

if __name__ == '__main__':
    main()
