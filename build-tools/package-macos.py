"""Package the native Apple Silicon GUI and Metal helper on macOS."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--windowed','--name','Pawquanta-Wallet',str(root/'core_wallet.py')],check=True)
package=root/'dist/Pawquanta-Wallet.app/Contents/MacOS'
node=package/'node';node.mkdir()
shutil.copy2(root/'build/bin/bitcoind',node/'pawquanta-node')
shutil.copy2(root/'build/bin/bitcoin-cli',node/'pawquanta-cli')
subprocess.run([sys.executable,str(root/'build-tools/build-metal.py'),str(package/'Pawquanta-Metal')],check=True)
manifest=json.loads((root/'core-release.json').read_text())
manifest.update(windows_node_file='node/pawquanta-node',windows_node_sha256=hashlib.sha256((node/'pawquanta-node').read_bytes()).hexdigest(),desktop_source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip())
(package/'core-release.json').write_text(json.dumps(manifest,indent=2)+'\n')
# Bundle non-system Homebrew dependencies and rewrite Mach-O paths. Do this
# before ad-hoc signing; no dependency on the build machine's /opt/homebrew.
pending=[node/'pawquanta-node',node/'pawquanta-cli'];seen=set();library=package/'native-libs';library.mkdir()
while pending:
    binary=pending.pop()
    if str(binary) in seen:continue
    seen.add(str(binary))
    lines=subprocess.check_output(['otool','-L',str(binary)],text=True).splitlines()[1:]
    for line in lines:
        dependency=line.strip().split(' (')[0]
        if dependency.startswith(('/opt/homebrew/','/usr/local/')):
            target=library/Path(dependency).name
            if not target.exists():shutil.copy2(dependency,target);pending.append(target)
            relative='@loader_path/'+('../native-libs/' if binary.parent==node else '')+target.name
            subprocess.run(['install_name_tool','-change',dependency,relative,str(binary)],check=True)
    if binary.suffix=='.dylib':subprocess.run(['install_name_tool','-id','@rpath/'+binary.name,str(binary)],check=True)
for binary in [*library.iterdir(),*node.iterdir(),package/'Pawquanta-Metal']:
    subprocess.run(['codesign','--force','--sign','-',str(binary)],check=True)
# install_name_tool and codesign change the executable bytes. Pin the final
# signed node, then seal the enclosing application with that manifest included.
manifest['windows_node_sha256']=hashlib.sha256((node/'pawquanta-node').read_bytes()).hexdigest()
(package/'core-release.json').write_text(json.dumps(manifest,indent=2)+'\n')
subprocess.run(['codesign','--force','--deep','--sign','-',str(root/'dist/Pawquanta-Wallet.app')],check=True)
check=root/'mac-wallet-selftest'
subprocess.run([str(package/'Pawquanta-Wallet'),'--self-test','--self-test-data',str(check)],check=True,timeout=300)
assert json.loads((check/'self-test-result.json').read_text())['passed']
shutil.copy2(root/'core/COPYING',root/'dist/CORE-LICENSE.txt')
(root/'dist/START-HERE.txt').write_text('Pawquanta Mainnet — experimental Apple Silicon preview\nOpen Pawquanta-Wallet.app, Connect, then optionally select Apple Metal GPU and Start mining.\nNot notarized. GPU must pass the on-device SHA256d self-check before mining.\nApple GPU hardware has not been verified on this build host. No M5 Max performance claim.\nWallet data: ~/Library/Application Support/Pawquanta. Keep backups and password private.\nStop mining stops hashing; no clock/fan/voltage changes.\n')
subprocess.run(['ditto','-c','-k','--sequesterRsrc','--keepParent',str(root/'dist/Pawquanta-Wallet.app'),str(root/'Pawquanta-Wallet-macOS-Apple-Silicon.zip')],check=True)
