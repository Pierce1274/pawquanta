"""Reproducible Windows wallet build using the unchanged verified Core backend."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile
root=Path(__file__).resolve().parents[1]
archive=root/'verified-core-base.zip'
urllib.request.urlretrieve('https://github.com/Pierce1274/pawquanta/releases/download/mainnet-v0.2.0/Pawquanta-Wallet-Windows-x64.zip',archive)
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='3f221a5b4b12eccf51dc15f20c11d47cdb090ba813bc87d51b740d2554e5d20e'
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--windowed','--name','Pawquanta-Wallet',
    '--collect-all','pyopencl','--collect-all','tuf','--collect-all','securesystemslib',str(root/'core_wallet.py')],check=True)
package=root/'dist/Pawquanta-Wallet';(package/'node').mkdir()
with zipfile.ZipFile(archive) as bundle:
    for name in ('Pawquanta-node.exe','Pawquanta-cli.exe'):
        (package/'node'/name).write_bytes(bundle.read('Pawquanta-Wallet/node/'+name))
manifest=json.loads((root/'core-release.json').read_text())
commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
manifest.update(windows_node_file='node/Pawquanta-node.exe',desktop_source_commit=commit,release_url='https://github.com/Pierce1274/pawquanta/releases/tag/mainnet-v0.4.2',wallet_version='0.4.2')
assert hashlib.sha256((package/'node/Pawquanta-node.exe').read_bytes()).hexdigest()==manifest['windows_node_sha256']
(package/'core-release.json').write_text(json.dumps(manifest,indent=2)+'\n')
for source,destination in [('update-root.json','update-root.json'),('core/COPYING','CORE-LICENSE.txt'),('GPU-MINING.md','GPU-MINING.md'),('UPDATES-AND-SECURITY.md','UPDATES-AND-SECURITY.md')]:shutil.copy2(root/source,package/destination)
check=root/'windows-wallet-selftest'
subprocess.run([str(package/'Pawquanta-Wallet.exe'),'--self-test','--self-test-data',str(check)],check=True,timeout=300)
result=json.loads((check/'self-test-result.json').read_text())
assert result['passed'] and result['real_reorg_alarm_persisted'] and result['minimum_12_confirmation_send']
subprocess.run([str(package/'Pawquanta-Wallet.exe'),'--ui-smoke'],check=True,timeout=30)
shutil.make_archive(str(root/'Pawquanta-Wallet-Windows-x64'),'zip',root/'dist','Pawquanta-Wallet')
