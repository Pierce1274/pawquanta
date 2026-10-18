import hashlib
from pathlib import Path
import tempfile
import unittest
from core_runtime import CoreRuntime,MAIN_GENESIS


class RuntimeSafety(unittest.TestCase):
    def test_existing_unrelated_files_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            binary=root/'dummy-node'
            binary.write_bytes(b'constructor-only test; never executed')
            digest=hashlib.sha256(binary.read_bytes()).hexdigest()
            personal=root/'personal'
            personal.mkdir()
            file=personal/'important.txt'
            file.write_text('keep this')
            with self.assertRaisesRegex(ValueError,'files were preserved'):
                CoreRuntime(personal,binary,digest,seed='127.0.0.1:18731')
            self.assertEqual(file.read_text(),'keep this')
            self.assertEqual(list(personal.iterdir()),[file])

    def test_identity_mismatch_does_not_reuse_wallet_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            binary=root/'dummy-node'
            binary.write_bytes(b'constructor-only')
            digest=hashlib.sha256(binary.read_bytes()).hexdigest()
            data=root/'owned'
            first=CoreRuntime(data,binary,digest,seed='127.0.0.1:18731')
            first.stop()
            CoreRuntime(data,binary,digest,seed='127.0.0.1:18731').stop()
            with self.assertRaisesRegex(ValueError,'files were preserved'):
                CoreRuntime(data,binary,digest,genesis='wrong',development=True)
            with self.assertRaisesRegex(ValueError,'verified package'):
                CoreRuntime(root/'unused',binary,'0'*64)
            self.assertFalse((root/'unused').exists())


if __name__=='__main__':unittest.main()
