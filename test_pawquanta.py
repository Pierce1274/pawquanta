import copy
import json
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from urllib.error import HTTPError
from hypothesis import given, strategies as st, settings
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import pawquanta as p

def key_address(key):
    return p.address(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw))

class Consensus(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        self.a = key_address(self.key)
        self.b = key_address(Ed25519PrivateKey.from_private_bytes(bytes(range(1,33))))
        self.chain = [copy.deepcopy(p.GENESIS)]
        for _ in range(4): self.chain.append(p.mine(self.chain,self.a))

    def test_payment_fees_and_maturity(self):
        self.assertEqual(p.validate(self.chain)['balances'][self.a],40*p.UNIT)
        tx = p.sign(self.key,self.b,10*p.UNIT,0,p.UNIT)
        self.chain.append(p.mine(self.chain,self.a,[tx]))
        state = p.validate(self.chain)
        self.assertEqual(state['balances'][self.b],10*p.UNIT)
        self.assertEqual(state['balances'][self.a],69*p.UNIT)
        self.assertEqual(state['pending'][-1][2],41*p.UNIT)

    def test_replay_double_spend_forgery_domain(self):
        tx = p.sign(self.key,self.b,10*p.UNIT,0)
        with self.assertRaises(ValueError): p.mine(self.chain,self.a,[tx,tx])
        forged = dict(tx,amount=11*p.UNIT)
        self.assertFalse(p.verify_tx(forged))
        self.assertFalse(p.verify_tx(dict(tx,network='mainnet')))
        block = p.mine(self.chain,self.a,[tx]); self.chain.append(block)
        with self.assertRaises(ValueError): p.mine(self.chain,self.a,[tx])
        with self.assertRaises(ValueError): p.mine(self.chain,self.a,[p.sign(self.key,self.b,p.CAP,1)])

    def test_immature_reward(self):
        chain = self.chain[:2]
        with self.assertRaises(ValueError): p.mine(chain,self.a,[p.sign(self.key,self.b,1,0)])

    def test_inflation_timewarp_orphan_and_schema(self):
        block = p.mine(self.chain,self.a)
        for changes in ({'target':p.MAX_TARGET},{'timestamp':int(time.time())+121},
                        {'previous':'f'*64},{'height':True},{'reward':p.CAP},
                        {'timestamp':0},{'nonce':-1},{'miner':'pqua_'+'z'*40}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                p.validate(self.chain+[dict(block,**changes)])
        with self.assertRaises(ValueError): p.strict_load('{"x":1,"x":2}')
        with self.assertRaises(ValueError): p.strict_load('{"x":NaN}')

    def test_supply_and_halving(self):
        self.assertEqual(p.subsidy(525000),40*p.UNIT)
        self.assertEqual(p.subsidy(525001),20*p.UNIT)
        self.assertLessEqual(p.emission_total(),p.CAP)
        self.assertEqual(p.emission_total(),4199999993175000)
        self.assertEqual(p.subsidy(525000*32+1),0)

    def test_retarget_bounds(self):
        # Pure target function vectors; no expensive mining needed.
        chain = [dict(p.GENESIS)]
        for h in range(1,121): chain.append(dict(p.GENESIS,height=h,timestamp=h*60))
        self.assertEqual(p.next_target(chain),p.INITIAL_TARGET)
        chain[-1]['timestamp'] = 60
        self.assertEqual(p.next_target(chain),p.INITIAL_TARGET//4)
        chain[-1]['timestamp'] = 1000000
        self.assertEqual(p.next_target(chain),p.INITIAL_TARGET*4)

    def test_reorg_and_restart(self):
        with tempfile.TemporaryDirectory() as d:
            n = p.Node(Path(d)/'chain.json')
            tx = p.sign(self.key,self.b,p.UNIT,0)
            branch = self.chain+[p.mine(self.chain,self.a,[tx])]
            self.assertTrue(n.accept_chain(branch))
            other = copy.deepcopy(self.chain)
            for _ in range(2): other.append(p.mine(other,self.b))
            self.assertTrue(n.accept_chain(other))
            self.assertNotIn(self.b,p.validate(other)['balances'])
            self.assertEqual(n.pool,[tx])
            reloaded = p.Node(Path(d)/'chain.json')
            self.assertEqual(p.sha(reloaded.chain[-1]),p.sha(other[-1]))
            self.assertFalse(n.accept_chain(branch))

    def test_equal_work_convergence(self):
        with tempfile.TemporaryDirectory() as d:
            x=p.Node(Path(d)/'x'); y=p.Node(Path(d)/'y')
            a=self.chain+[p.mine(self.chain,self.a)]
            b=self.chain+[p.mine(self.chain,self.b)]
            x.accept_chain(a); x.accept_chain(b)
            y.accept_chain(b); y.accept_chain(a)
            self.assertEqual(x.chain,y.chain)

    @settings(max_examples=40,deadline=None)
    @given(st.integers(min_value=1,max_value=39*p.UNIT),st.integers(min_value=0,max_value=p.UNIT))
    def test_property_conservation(self,amount,fee):
        balances={self.a:40*p.UNIT}; nonces={}
        tx=p.sign(self.key,self.b,amount,0,fee)
        p.apply_tx(tx,balances,nonces)
        self.assertEqual(sum(balances.values())+fee,40*p.UNIT)
        self.assertEqual(nonces[self.a],1)

    @settings(max_examples=40,deadline=None)
    @given(st.one_of(st.booleans(),st.text(max_size=40),st.floats(allow_nan=False),st.none()))
    def test_property_reject_amount_types(self,amount):
        tx=p.sign(self.key,self.b,1,0); tx['amount']=amount
        self.assertFalse(p.verify_tx(tx))

class WalletAndNetwork(unittest.TestCase):
    def test_published_consensus_vectors(self):
        vectors=json.loads((Path(__file__).parent/'vectors.json').read_text())
        self.assertEqual(p.sha(p.GENESIS),vectors['genesis_hash'])
        self.assertEqual(p.sha(vectors['chain'][-1]),vectors['tip'])
        self.assertEqual(p.pow_bytes(vectors['chain'][-1]).hex(),vectors['pow_hash'])
        self.assertEqual(p.validate(vectors['chain'],now=300)['balances'],vectors['state']['balances'])
        self.assertEqual(p.canonical(vectors['chain'][-1]).decode(),vectors['canonical_last_block'])

    def test_encrypted_wallet(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'wallet.pem'; pw='test-password-only-123'
            addr=p.new_wallet(path,pw)
            self.assertIn(b'ENCRYPTED PRIVATE KEY',path.read_bytes())
            self.assertEqual(key_address(p.load_wallet(path,pw)),addr)
            with self.assertRaises(ValueError): p.load_wallet(path,'wrong')
            with self.assertRaises(FileExistsError): p.new_wallet(path,pw)

    def test_http_sync_partition_recovery_and_invalid_peer(self):
        with tempfile.TemporaryDirectory() as d:
            token='test-only-key-'+('x'*24)
            a=p.Node(Path(d)/'a',token=token); b=p.Node(Path(d)/'b',token=token)
            servers=[p.Server(('127.0.0.1',0),n) for n in (a,b)]
            for server in servers: threading.Thread(target=server.serve_forever,daemon=True).start()
            urls=['http://127.0.0.1:'+str(s.server_port) for s in servers]
            try:
                key=Ed25519PrivateKey.generate(); addr=key_address(key)
                chain=[copy.deepcopy(p.GENESIS)]
                for _ in range(4): chain.append(p.mine(chain,addr))
                a.accept_chain(chain)
                # Partition: b can only reach an unavailable peer, cannot discover an honest one.
                b.peers=('http://127.0.0.1:1',); b.sync_once(); self.assertEqual(len(b.chain),1)
                b.peers=(urls[0],); b.sync_once(); self.assertEqual(a.chain,b.chain)
                tx=p.sign(key,addr,1,0)
                p.request(urls[0],'/tx',tx,token)
                b.sync_once(); self.assertEqual(b.pool,[tx])
                with self.assertRaises(HTTPError) as error: p.request(urls[0],'/tx',tx,'bad')
                self.assertEqual(error.exception.code,403)
                with self.assertRaises(HTTPError): p.request(urls[0],'/block',{'bad':True},token)
                with self.assertRaises(HTTPError) as error: p.request(urls[0],'/block',[],token)
                self.assertEqual(error.exception.code,400)
                duplicate=urllib.request.Request(urls[0]+'/tx',data=b'{"nonce":0,"nonce":1}',headers={'X-PQUA-Key':token})
                with self.assertRaises(HTTPError) as error: urllib.request.urlopen(duplicate,timeout=4)
                self.assertEqual(error.exception.code,400)
                self.assertTrue(p.request(urls[0],'/status')['testnet_only'])
                # Incompatible network handshake cannot replace local state.
                old=p.sha(b.chain[-1]); b.token='bad'; b.sync_once()
                self.assertEqual(p.sha(b.chain[-1]),old)
                # Deterministic rate-limit boundary without sending 240 requests.
                servers[0].rates['127.0.0.1']=(int(time.time())//60,240)
                with self.assertRaises(HTTPError) as error: p.request(urls[0],'/status')
                self.assertEqual(error.exception.code,429)
            finally:
                for server in servers: server.shutdown(); server.server_close()

if __name__ == '__main__': unittest.main()
