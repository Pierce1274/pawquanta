"""User-controllable TUF-verified application updates; no wallet migration."""
import json
import os
from pathlib import Path,PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import threading
import zipfile
import uuid
import unicodedata
from tuf.ngclient import Updater

VERSION='0.4.2'
SERIAL=42
METADATA_URL='https://raw.githubusercontent.com/Pierce1274/pawquanta/wallet-updates/metadata/'
TARGET_URL='https://github.com/Pierce1274/pawquanta/releases/download/'
CHANNEL_URL='https://raw.githubusercontent.com/Pierce1274/pawquanta/wallet-updates/targets/'
MAX_EXPANDED=512*1024*1024

def platform_name():
    return 'macos-arm64' if sys.platform=='darwin' else 'windows-x64'

def version_tuple(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d+\.\d+\.\d+',value):raise ValueError('Invalid release version')
    return tuple(map(int,value.split('.')))

def validate_release(custom,current=VERSION):
    from core_runtime import MAIN_GENESIS
    if custom.get('genesis')!=MAIN_GENESIS:raise ValueError('Update belongs to another network')
    if type(custom.get('serial')) is not int or custom['serial']<SERIAL:raise ValueError('Update rollback refused')
    version_tuple(custom['version'])
    if version_tuple(custom['version'])<=version_tuple(current):return False
    if custom.get('protocol_change') is not False:raise ValueError('Protocol changes require a separate manual upgrade')
    return True

def extract_package(archive,destination,platform):
    """Fresh directory only; reject path escapes, aliases, bombs and link traversal."""
    destination=Path(destination).resolve()
    if destination.exists():raise ValueError('Update destination already exists; preserved it')
    root='Pawquanta-Wallet.app' if platform=='macos-arm64' else 'Pawquanta-Wallet'
    with zipfile.ZipFile(archive) as bundle:
        members=bundle.infolist()
        if len(members)>12000 or sum(m.file_size for m in members)>MAX_EXPANDED:raise ValueError('Update archive exceeds limits')
        paths=set();links={}
        for item in members:
            name=PurePosixPath(item.filename)
            if '\\' in item.filename or ':' in item.filename or name.is_absolute() or '..' in name.parts or not name.parts:raise ValueError('Unsafe archive path')
            if any(part.endswith((' ','.')) or part.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]} for part in name.parts):raise ValueError('Unsafe platform filename')
            # Mac ZIP may contain separately supplied notices and Apple metadata.
            if name.parts[0]!=root:
                if platform=='macos-arm64' and (name.parts[0]=='__MACOSX' or str(name) in ('CORE-LICENSE.txt','START-HERE.txt','GPU-MINING.md')):continue
                raise ValueError('Unexpected update package root')
            key=unicodedata.normalize('NFC',str(name)).casefold()
            if key in paths:raise ValueError('Duplicate archive path')
            paths.add(key)
            if stat.S_ISLNK(item.external_attr>>16):
                if platform!='macos-arm64' or item.file_size>4096:raise ValueError('Unsupported update symlink')
                target=bundle.read(item).decode('utf-8')
                if '\\' in target or ':' in target or Path(target).is_absolute():raise ValueError('Unsafe symlink')
                resolved=(destination/str(name)).parent.joinpath(target).resolve()
                if not resolved.is_relative_to(destination/root):raise ValueError('Symlink escapes application')
                links[str(name)]=target
        for key in paths:
            if any(key.startswith(link.casefold()+'/') for link in links):raise ValueError('Archive writes through symlink')
        destination.mkdir(parents=True)
        for item in members:
            name=PurePosixPath(item.filename)
            if name.parts[0]!=root or str(name) in links:continue
            output=destination.joinpath(*name.parts)
            if item.is_dir():output.mkdir(parents=True,exist_ok=True)
            else:
                output.parent.mkdir(parents=True,exist_ok=True)
                with bundle.open(item) as source,output.open('xb') as target:shutil.copyfileobj(source,target)
                if platform=='macos-arm64':output.chmod((item.external_attr>>16)&0o755)
        for name,target in links.items():
            output=destination/name;output.parent.mkdir(parents=True,exist_ok=True);output.symlink_to(target)
        for name in links:
            if not (destination/name).resolve().is_relative_to(destination/root):raise ValueError('Resolved symlink escapes application')
    executable=destination/root/('Contents/MacOS/Pawquanta-Wallet' if platform=='macos-arm64' else 'Pawquanta-Wallet.exe')
    if not executable.is_file():raise ValueError('Update has no wallet executable')
    return executable

class WalletUpdates:
    def __init__(self,store,bootstrap,status=lambda value:None):
        self.store=Path(store).resolve();self.bootstrap=bytes(bootstrap);self.status=status;self.lock=threading.Lock()
        from core_runtime import private_directory,MAIN_GENESIS
        marker=self.store/'.pawquanta-updates.json'
        if self.store.exists() and any(self.store.iterdir()) and not marker.exists():raise ValueError('Unrecognized update folder; existing files preserved')
        private_directory(self.store)
        identity={'genesis':MAIN_GENESIS,'schema':1}
        if marker.exists() and json.loads(marker.read_text())!=identity:raise ValueError('Update folder identity mismatch')
        if not marker.exists():marker.write_text(json.dumps(identity))
        self.settings=self.store/'preferences.json'

    def enabled(self):
        return json.loads(self.settings.read_text()).get('automatic',True) if self.settings.exists() else True

    def set_enabled(self,value):self.settings.write_text(json.dumps({'automatic':bool(value)}))

    def client(self):
        metadata=self.store/'metadata';metadata.mkdir(exist_ok=True)
        return Updater(str(metadata),METADATA_URL,target_base_url=TARGET_URL,bootstrap=self.bootstrap)

    def check(self):
        from core_miner import exclusive_miner
        with self.lock,exclusive_miner(self.store/'update-operation'):
            client=self.client();client.refresh()
            channel=client.get_targetinfo('channel.json')
            if channel is None:raise ValueError('No approved update channel')
            path=client.download_target(channel,str(self.store/'channel.json'),target_base_url=CHANNEL_URL)
            release=json.loads(Path(path).read_text());custom=release['release']
            if not validate_release(custom):return None
            name=release['packages'][platform_name()]
            if not re.fullmatch(r'mainnet-v\d+\.\d+\.\d+/[A-Za-z0-9._-]+\.zip',name):raise ValueError('Invalid approved package path')
            target=client.get_targetinfo(name)
            if target is None or target.length>128*1024*1024:raise ValueError('Approved package missing or too large')
            self.status('Downloading approved update '+custom['version'])
            downloaded=client.download_target(target,str(self.store/'approved-update.zip'))
            pending={'release':custom,'target':target.to_dict(),'path':target.path,'archive':str(downloaded)}
            (self.store/'pending.json').write_text(json.dumps(pending,indent=2))
            return custom

    def install(self,current=VERSION):
        from core_miner import exclusive_miner
        with self.lock,exclusive_miner(self.store/'update-operation'):
            return self._install(current)

    def _install(self,current=VERSION):
        """Called only after miner, wallet node and transport close cleanly."""
        from tuf.api.metadata import TargetFile
        pending=json.loads((self.store/'pending.json').read_text())
        if not validate_release(pending['release'],current):return None
        client=self.client();client.refresh()
        info=client.get_targetinfo(pending['path'])
        if info is None or info.to_dict()!=pending['target']:raise ValueError('Approval changed; installation cancelled')
        archive=Path(pending['archive']).resolve()
        if archive!=self.store/'approved-update.zip':raise ValueError('Unexpected update staging path')
        with archive.open('rb') as stream:info.verify_length_and_hashes(stream)
        if shutil.disk_usage(self.store).free<MAX_EXPANDED:raise RuntimeError('Not enough disk space to stage an update safely')
        destination=self.store/'versions'/(pending['release']['version']+'-'+uuid.uuid4().hex)
        executable=extract_package(archive,destination,platform_name())
        if platform_name()=='macos-arm64':subprocess.run(['codesign','--verify','--deep','--strict',str(destination/'Pawquanta-Wallet.app')],check=True,timeout=30)
        (self.store/'installed.json').write_text(json.dumps({'version':pending['release']['version'],'executable':str(executable)}))
        return executable

    def installed(self):
        path=self.store/'installed.json'
        if not path.exists():return None
        value=json.loads(path.read_text())
        if version_tuple(value['version'])<=version_tuple(VERSION):return None
        executable=Path(value['executable']).resolve()
        if not executable.is_relative_to(self.store/'versions') or not executable.is_file():raise ValueError('Invalid installed update location')
        return executable

def launch(executable,profile,store,resume_connection=False,resume_mining=False):
    args=[str(executable),'--wallet-directory',str(profile),'--update-directory',str(store)]
    if resume_connection:args.append('--resume-connection')
    if resume_mining:args.append('--resume-mining')
    subprocess.Popen(args,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
