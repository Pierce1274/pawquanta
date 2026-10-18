import tempfile
import unittest
from pathlib import Path
from decimal import Decimal
import core_miner as m


class FakeChain:
    def __init__(self):
        self.genesis = 'genesis-a'
        self.blocks = []

    def add(self, name, reward, script='0014abc'):
        self.blocks.append({'hash': name, 'height': len(self.blocks) + 1,
            'tx': [{'vin': [{'coinbase': '01'}], 'vout': [
                {'value': Decimal(reward), 'scriptPubKey': {'hex': script}}]},
                {'vin': [{'txid': 'ordinary-transfer'}], 'vout': [
                {'value': Decimal('900'), 'scriptPubKey': {'hex': '0014abc'}}]}]})

    def __call__(self, method, *args):
        if method == 'getblockcount':
            return len(self.blocks)
        if method == 'getbestblockhash':
            return self.blocks[-1]['hash'] if self.blocks else self.genesis
        if method == 'getblockhash':
            return self.blocks[args[0] - 1]['hash'] if args[0] else self.genesis
        if method == 'getblock':
            return next(b for b in self.blocks if b['hash'] == args[0])
        raise AssertionError(method)


class MinerTests(unittest.TestCase):
    def test_owner_cap_is_fixed_while_other_users_choose_their_own_budget(self):
        self.assertEqual(m.mining_limit(m.APPROVED_LIMIT),m.APPROVED_LIMIT)
        with self.assertRaises(ValueError):m.mining_limit(m.APPROVED_LIMIT+1)
        self.assertEqual(m.mining_limit(42_000_000*m.UNIT,False),42_000_000*m.UNIT)
        for invalid in (True,1.5,-1,42_000_000*m.UNIT+1):
            with self.assertRaises(ValueError):m.mining_limit(invalid,False)
    def test_canonical_earnings_restart_reorg_and_network_switch(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'earnings.sqlite'
            chain = FakeChain()
            ledger = m.RewardLedger(file, chain.genesis, '0014abc')
            chain.add('a', '40.125')  # Subsidy plus fee, including immature coins.
            chain.add('b', '40', 'other-miner')
            self.assertEqual(ledger.sync(chain), ('b', 4_012_500_000))
            ledger.db.close()
            ledger = m.RewardLedger(file, chain.genesis, '0014abc')
            self.assertEqual(ledger.sync(chain)[1], 4_012_500_000)
            chain.blocks.clear()  # Winning fork replaces our earlier reward.
            chain.add('c', '40', 'other-miner')
            chain.add('d', '40.00000001')
            self.assertEqual(ledger.sync(chain), ('d', 4_000_000_001))
            chain.genesis = 'different-network'
            with self.assertRaisesRegex(ValueError, 'changed networks'):
                ledger.sync(chain)
            ledger.db.close()
            with self.assertRaisesRegex(ValueError, 'different genesis'):
                m.RewardLedger(file, 'wrong-genesis', '0014abc')

    def test_coinbase_and_pow_boundaries(self):
        self.assertEqual(m.height_script(1), b'\x51')
        self.assertEqual(m.height_script(128), b'\x02\x80\x00')
        for bits in ['00000000', '1d80ffff', '2300ffff']:
            with self.assertRaises(ValueError):
                m.target_from_bits(bits)
        template = {'height': 128, 'coinbasevalue': 40 * m.UNIT,
                    'transactions': [], 'version': 0x20000000,
                    'previousblockhash': '00' * 32, 'curtime': 1792335600,
                    'bits': '207fffff', 'default_witness_commitment': '6a24aa21a9ed' + '00' * 32}
        for reward in [True, -1, 40 * m.UNIT + 1, 1.5]:
            with self.assertRaises(ValueError):
                m.candidate(template, '51', reward)
        header, body = m.candidate(template, '51', 1, bytes(12))
        self.assertEqual(len(header), 76)
        self.assertEqual(body[0], 1)
        self.assertEqual(body[5:7], b'\x00\x01')  # Witness marker in serialized coinbase.
        self.assertEqual(m.merkle_root([b'a' * 32]), b'a' * 32)

    def test_exclusive_miner(self):
        with tempfile.TemporaryDirectory() as directory:
            with m.exclusive_miner(Path(directory) / 'ledger'):
                with self.assertRaises(OSError):
                    with m.exclusive_miner(Path(directory) / 'ledger'):
                        self.fail('Second miner acquired the same quota lock')

    def test_management_rpc_stays_private(self):
        for url in ['http://192.168.68.56:18732', 'https://example.com',
                    'http://user:password@127.0.0.1:18732']:
            with self.assertRaises(ValueError):
                m.RPC(url, 'unused')


if __name__ == '__main__':
    unittest.main()
