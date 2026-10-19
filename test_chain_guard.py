import tempfile
from pathlib import Path
import unittest
from chain_guard import ChainGuard
from core_runtime import MAIN_GENESIS

class Chain:
    def __init__(self):self.blocks=[MAIN_GENESIS]+['block-'+str(i) for i in range(1,20)]
    def __call__(self,name,*args):
        if name=='getblockcount':return len(self.blocks)-1
        if name=='getblockhash':return self.blocks[args[0]]
        raise AssertionError(name)

class GuardTests(unittest.TestCase):
    def test_reorg_latches_across_restart_and_requires_explicit_review(self):
        with tempfile.TemporaryDirectory() as d:
            chain=Chain();path=Path(d)/'monitor.json';guard=ChainGuard(path)
            guard.require_payments(chain);chain.blocks.append('new-tip');guard.require_payments(chain)
            chain.blocks[-1]='replacement'
            with self.assertRaisesRegex(RuntimeError,'history changed'):guard.require_payments(chain)
            guard=ChainGuard(path)
            with self.assertRaises(RuntimeError):guard.require_payments(chain)
            guard.acknowledge(chain);guard.require_payments(chain)
    def test_lower_height_and_wrong_network_are_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            chain=Chain();guard=ChainGuard(Path(d)/'monitor.json');guard.observe(chain)
            chain.blocks=chain.blocks[:3]
            with self.assertRaises(RuntimeError):guard.require_payments(chain)
            chain.blocks[0]='other-chain'
            with self.assertRaises(ValueError):guard.observe(chain)

if __name__=='__main__':unittest.main()
