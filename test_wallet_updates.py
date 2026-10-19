import contextlib
from datetime import datetime,timedelta,timezone
import http.server
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile
from wallet_updates import WalletUpdates,extract_package

class UpdatesTests(unittest.TestCase):
    def test_existing_personal_folder_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'personal.txt';file.write_text('keep this')
            with self.assertRaises(ValueError):WalletUpdates(d,b'not used')
            self.assertEqual(file.read_text(),'keep this')

    def test_archive_escape_and_duplicate_paths_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d)
            for names in (['../escape'],['Pawquanta-Wallet/a','Pawquanta-Wallet/A']):
                with zipfile.ZipFile(d/'bad.zip','w') as z:
                    for name in names:z.writestr(name,'fixture')
                with self.assertRaises(ValueError):extract_package(d/'bad.zip',d/'out','windows-x64')
                self.assertFalse((d/'out').exists())

    def test_tuf_approved_update_install_and_tamper_rejection(self):
        spec=importlib.util.spec_from_file_location('approval_fixture',Path(__file__).parent/'build-tools/approve-wallet-release.py')
        approval=importlib.util.module_from_spec(spec);spec.loader.exec_module(approval)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);approval.ROOT=root;approval.PRIVATE=root/'private';approval.FEED=root/'feed';approval.initialize()
            binary=root/'Pawquanta-Wallet-Windows-x64.zip'
            with zipfile.ZipFile(binary,'w') as bundle:bundle.writestr('Pawquanta-Wallet/Pawquanta-Wallet.exe',b'benign fixture; never executed')
            password=(approval.PRIVATE/'approval-password.txt').read_bytes().strip()
            approval.approve('0.4.3',43,binary,binary,password)
            package=approval.FEED/'packages/mainnet-v0.4.3';package.mkdir(parents=True)
            (package/binary.name).write_bytes(binary.read_bytes())
            import functools
            class Handler(http.server.SimpleHTTPRequestHandler):
                def log_message(self,*args):pass
            server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(approval.FEED)))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base='http://127.0.0.1:'+str(server.server_port)+'/'
            try:
                with patch('wallet_updates.METADATA_URL',base+'metadata/'),patch('wallet_updates.TARGET_URL',base+'packages/'),patch('wallet_updates.CHANNEL_URL',base+'targets/'),patch('wallet_updates.platform_name',return_value='windows-x64'):
                    client=WalletUpdates(root/'client',(root/'update-root.json').read_bytes())
                    self.assertEqual(client.check()['version'],'0.4.3')
                    archive=client.store/'approved-update.zip';valid=archive.read_bytes();archive.write_bytes(valid+b'tamper')
                    with self.assertRaises(Exception):client.install()
                    archive.write_bytes(valid);exe=client.install();self.assertTrue(exe.is_file())
                    self.assertEqual(client.installed(),exe)
                    self.assertFalse((root/'client/Pawquanta-wallet-data').exists())
                    from tuf.api.metadata import Metadata
                    timestamp=approval.FEED/'metadata/timestamp.json';original_stamp=timestamp.read_bytes()
                    expired=Metadata.from_bytes(original_stamp);expired.signed.expires=datetime.now(timezone.utc)-timedelta(days=1)
                    expired.sign(approval.signer('timestamp'));expired.to_file(str(timestamp))
                    with self.assertRaises(Exception):WalletUpdates(root/'expired',(root/'update-root.json').read_bytes()).check()
                    timestamp.write_bytes(original_stamp)
                    # A cached newer timestamp cannot be replaced by an older signed one.
                    approval.renew();client.client().refresh();timestamp.write_bytes(original_stamp)
                    with self.assertRaises(Exception):client.client().refresh()
                    approval.renew()
                    # Corrupt signed targets metadata: a clean client must refuse it.
                    targets=approval.FEED/'metadata/targets.json';original=targets.read_bytes();targets.write_bytes(original.replace(b'0.4.3',b'0.4.9'))
                    other=WalletUpdates(root/'other',(root/'update-root.json').read_bytes())
                    with self.assertRaises(Exception):other.check()
            finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
