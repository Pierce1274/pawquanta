import base64,csv,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock
from cryptography.exceptions import InvalidTag
from core_runtime import MAIN_GENESIS
import wallet_v1 as f
import mining_plan

class WalletV1Tests(unittest.TestCase):
    def test_encrypted_backup_restores_separately_and_preserves_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);profile=root/'source';profile.mkdir();(profile/'wallet-recovery-password.txt').write_text('private wallet password');(profile/'wallet-receiving-address.txt').write_text('fixture-address')
            (profile/'mining-preferences.json').write_text('{"limit_atomic_units":123}')
            runtime=Mock();runtime.genesis=MAIN_GENESIS
            def wallet(method,*args):
                if method=='backupwallet':Path(args[0]).write_bytes(b'encrypted-native-wallet-fixture')
                if method=='getwalletinfo':return {'walletname':'wallet'}
            runtime.wallet.side_effect=wallet;backup=root/'bundle.pquabackup';secret='testing backup phrase 123'
            body=f.make_backup(runtime,profile,secret,backup)
            self.assertNotIn(b'private wallet password',backup.read_bytes())
            with self.assertRaises(InvalidTag):f.read_backup(backup,'different password 123')
            restored=f.restore_backup(body,root/'restored')
            self.assertEqual((restored/'wallet-recovery-password.txt').read_text().strip(),'private wallet password')
            self.assertEqual((restored/'node/wallets/wallet/wallet.dat').read_bytes(),b'encrypted-native-wallet-fixture')
            self.assertTrue((restored/'STOP-MINING').exists())
            with self.assertRaises(ValueError):f.restore_backup(body,restored)
            with self.assertRaises(ValueError):f.make_backup(runtime,profile,secret,backup)
            raw=bytearray(backup.read_bytes());raw[-1]^=1;(root/'corrupt').write_bytes(raw)
            with self.assertRaises(InvalidTag):f.read_backup(root/'corrupt',secret)

    def test_send_exact_fee_and_recipient_are_checked_before_broadcast(self):
        runtime=Mock();guard=Mock();runtime.rpc.return_value={'isvalid':True,'scriptPubKey':'0014'+'11'*20};runtime.wallet.return_value={'psbt':'prepared','fee':'0.00000213'}
        quote=f.prepare_send(runtime,guard,'fixture-address','1.00000001');self.assertEqual(quote['units'],100000001)
        self.assertEqual(runtime.wallet.call_args.args[4]['minconf'],12)
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'wallet-recovery-password.txt').write_text('private')
            runtime.wallet.side_effect=lambda method,*a: {'walletname':'wallet'} if method=='getwalletinfo' else {'psbt':'signed'} if method=='walletprocesspsbt' else None
            runtime.rpc.side_effect=lambda method,*a: {'complete':True,'hex':'raw'} if method=='finalizepsbt' else {'vout':[]} if method=='decoderawtransaction' else None
            with self.assertRaises(ValueError):f.confirm_send(runtime,guard,folder,quote)
            self.assertNotIn('sendrawtransaction',[c.args[0] for c in runtime.rpc.call_args_list])
            self.assertEqual(runtime.wallet.call_args.args[0],'walletlock')

    def test_schedules_stop_and_never_retroactively_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            plan=mining_plan.save(folder,1000,5,now=1000)
            self.assertEqual(mining_plan.phase(plan,999),'waiting');self.assertEqual(mining_plan.phase(plan,1001),'active');self.assertEqual(mining_plan.phase(plan,1300),'ended')
            mining_plan.cancel(folder);self.assertEqual(mining_plan.phase(mining_plan.read(folder),1100),'inactive')
            with self.assertRaises(ValueError):mining_plan.save(folder,float('nan'),1)
            with self.assertRaises(ValueError):mining_plan.save(folder,1000,0,now=1000)

    def test_csv_contacts_and_safe_profiles(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'records.csv';f.export_history(file,[{'label':'=HYPERLINK("bad")','amount':'-1.25','time':1}])
            with file.open(encoding='utf-8-sig') as stream:rows=list(csv.reader(stream))
            self.assertTrue(rows[1][6].startswith("'="));self.assertEqual(rows[1][2],'-1.25')
            rpc=Mock(return_value={'isvalid':True});f.save_contact(folder,'Friend','address',rpc);self.assertEqual(f.address_book(folder)[0]['label'],'Friend')
            (Path(folder)/'wallet-ui.json').write_text('invalid');self.assertEqual(f.preferences(folder)['theme'],'dark')
        self.assertFalse(f.mining_profile('Quiet',8)['manual_cpu']);self.assertEqual(f.mining_profile('Balanced',8)['cpu_workers'],4)
        for bad in ('NaN','0','-1','0.000000001','42000001'):
            with self.assertRaises(ValueError):f.amount_units(bad)

if __name__=='__main__':unittest.main()
