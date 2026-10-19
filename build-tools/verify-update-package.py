"""Exercise update extraction against the actual distributable, including Mac links."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wallet_updates import extract_package,platform_name

root=Path(__file__).resolve().parents[1]
platform=platform_name()
archive=root/('Pawquanta-Wallet-macOS-Apple-Silicon.zip' if platform=='macos-arm64' else 'Pawquanta-Wallet-Windows-x64.zip')
with tempfile.TemporaryDirectory(prefix='pawquanta-update-check-') as folder:
    executable=extract_package(archive,Path(folder)/'version',platform)
    original=root/('dist/Pawquanta-Wallet.app/Contents/MacOS/Pawquanta-Wallet' if platform=='macos-arm64' else 'dist/Pawquanta-Wallet/Pawquanta-Wallet.exe')
    assert hashlib.sha256(executable.read_bytes()).digest()==hashlib.sha256(original.read_bytes()).digest()
    if platform=='macos-arm64':
        subprocess.run(['codesign','--verify','--deep','--strict',str(executable.parents[2])],check=True)
    print('Actual update archive extracted and executable verified:',platform)
