import unittest, tempfile, os
import chonk
class Integration(unittest.TestCase):
 def test_mining_and_transfer(self):
  with tempfile.TemporaryDirectory() as d:
   a=os.path.join(d,'a.json');b=os.path.join(d,'b.json')
   aa=chonk.make_wallet(a);bb=chonk.make_wallet(b)
   blocks=[chonk.GENESIS];blocks.append(chonk.mine(blocks,aa))
   self.assertEqual(chonk.state(blocks)[0][aa],40)
   tx=chonk.sign_tx(a,bb,10,0)
   self.assertTrue(chonk.verify_tx(tx))
   blocks.append(chonk.mine(blocks,aa,[tx]))
   bal,_=chonk.state(blocks)
   self.assertEqual(bal[bb],10)
   self.assertEqual(bal[aa],70)
   with self.assertRaises(ValueError):chonk.state(blocks+[blocks[-1]])
 def test_halving(self):
  self.assertEqual(chonk.reward(1),40)
  self.assertEqual(chonk.reward(525000),20)
  self.assertEqual(chonk.reward(525000*6),0)
if __name__=='__main__':unittest.main()
