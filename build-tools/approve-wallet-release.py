"""Owner approval for TUF releases. Private keys never enter GitHub or packages."""
import argparse
from datetime import datetime,timedelta,timezone
import getpass
import json
import os
from pathlib import Path
import secrets
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from securesystemslib.signer import CryptoSigner
from tuf.api.metadata import Metadata,Root,Targets,Snapshot,Timestamp,TargetFile,MetaFile
from core_runtime import private_directory,MAIN_GENESIS

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=ROOT/'runtime/update-signing'
FEED=ROOT/'update-feed'

def signer(role,password=None):
    raw=(PRIVATE/(role+'.pem')).read_bytes()
    return CryptoSigner(serialization.load_pem_private_key(raw,password=password))

def initialize():
    private_directory(PRIVATE);(FEED/'metadata').mkdir(parents=True,exist_ok=True);(FEED/'targets').mkdir(exist_ok=True)
    if (PRIVATE/'root.pem').exists():raise ValueError('Existing approval keys preserved; refusing regeneration')
    password=secrets.token_urlsafe(36).encode()
    (PRIVATE/'approval-password.txt').write_bytes(password+b'\n')
    root=Metadata(Root(expires=datetime.now(timezone.utc)+timedelta(days=3650),consistent_snapshot=False))
    roles={}
    for role in ('root','targets','snapshot','timestamp'):
        key=Ed25519PrivateKey.generate()
        encryption=serialization.BestAvailableEncryption(password) if role in ('root','targets') else serialization.NoEncryption()
        (PRIVATE/(role+'.pem')).write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,encryption))
        roles[role]=CryptoSigner(key);root.signed.add_key(roles[role].public_key,role)
    root.sign(roles['root']);data=root.to_bytes()
    for path in (ROOT/'update-root.json',FEED/'metadata/root.json',FEED/'metadata/1.root.json'):path.write_bytes(data)
    print('Update trust root created. Approval/recovery material is in the protected local signing folder; no secret was printed.')

def renew():
    """Online keys can renew freshness, but cannot approve new application code."""
    metadata=FEED/'metadata';root=Metadata.from_file(str(metadata/'root.json'))
    targets=Metadata.from_file(str(metadata/'targets.json'));root.verify_delegate('targets',targets)
    now=datetime.now(timezone.utc)
    snapshot=Metadata.from_file(str(metadata/'snapshot.json')) if (metadata/'snapshot.json').exists() else Metadata(Snapshot())
    timestamp=Metadata.from_file(str(metadata/'timestamp.json')) if (metadata/'timestamp.json').exists() else Metadata(Timestamp())
    snapshot.signed.version+=1;snapshot.signed.expires=now+timedelta(days=365)
    snapshot.signed.meta={'targets.json':MetaFile.from_data(targets.signed.version,(metadata/'targets.json').read_bytes(),['sha256'])}
    snapshot.sign(signer('snapshot'));snapshot.to_file(str(metadata/'snapshot.json'))
    timestamp.signed.version+=1;timestamp.signed.expires=now+timedelta(days=30)
    timestamp.signed.snapshot_meta=MetaFile.from_data(snapshot.signed.version,(metadata/'snapshot.json').read_bytes(),['sha256'])
    timestamp.sign(signer('timestamp'));timestamp.to_file(str(metadata/'timestamp.json'))

def approve(version,serial,windows,mac,password):
    from wallet_updates import version_tuple
    version_tuple(version)
    if (FEED/'.git').exists():
        import subprocess
        subprocess.run(['git','-C',str(FEED),'pull','--ff-only','origin','wallet-updates'],check=True)
    if type(serial) is not int or serial<42:raise ValueError('Invalid release serial')
    metadata=FEED/'metadata';old=Metadata.from_file(str(metadata/'targets.json')) if (metadata/'targets.json').exists() else None
    if old and serial<=old.signed.version:raise ValueError('Approval serial must increase')
    release={'version':version,'serial':serial,'genesis':MAIN_GENESIS,'protocol_change':False}
    packages={'windows-x64':f'mainnet-v{version}/{windows.name}','macos-arm64':f'mainnet-v{version}/{mac.name}'}
    channel=FEED/'targets/channel.json';channel.write_text(json.dumps({'release':release,'packages':packages},indent=2)+'\n')
    targets=Metadata(Targets(version=serial,expires=datetime.now(timezone.utc)+timedelta(days=365)))
    for name,file in [('channel.json',channel),(packages['windows-x64'],windows),(packages['macos-arm64'],mac)]:
        targets.signed.targets[name]=TargetFile.from_file(name,str(file),['sha256'])
    targets.sign(signer('targets',password));targets.to_file(str(metadata/'targets.json'))
    renew();print('Approved application release',version,'with serial',serial)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['initialize','approve','renew'])
    parser.add_argument('--version');parser.add_argument('--serial',type=int);parser.add_argument('--windows',type=Path);parser.add_argument('--mac',type=Path)
    parser.add_argument('--initial-authorized-approval',action='store_true',help='Use only for the initial release explicitly requested in this session')
    args=parser.parse_args()
    if args.action=='initialize':initialize()
    elif args.action=='renew':renew()
    else:
        if args.initial_authorized_approval and (args.version!='0.4.2' or args.serial!=42 or (FEED/'metadata/targets.json').exists()):
            raise ValueError('Initial approval applies only once to the explicitly requested v0.4.2 release')
        password=(PRIVATE/'approval-password.txt').read_bytes().strip() if args.initial_authorized_approval else getpass.getpass('Release approval password: ').encode()
        approve(args.version,args.serial,args.windows.resolve(),args.mac.resolve(),password)
