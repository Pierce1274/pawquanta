"""Refresh online TUF roles without approval keys or authority to change targets."""
from datetime import datetime,timedelta,timezone
import os
from pathlib import Path
import subprocess
import sys
from cryptography.hazmat.primitives import serialization
from securesystemslib.signer import CryptoSigner
from tuf.api.metadata import Metadata,MetaFile

feed=Path(sys.argv[1]);metadata=feed/'metadata'
root=Metadata.from_file(str(metadata/'root.json'))
targets=Metadata.from_file(str(metadata/'targets.json'));root.verify_delegate('targets',targets)
now=datetime.now(timezone.utc)
if root.signed.expires<=now or targets.signed.expires<=now:raise RuntimeError('Approval metadata expired; operator approval is required')
snapshot=Metadata.from_file(str(metadata/'snapshot.json'));timestamp=Metadata.from_file(str(metadata/'timestamp.json'))
snapshot.signed.version+=1;snapshot.signed.expires=now+timedelta(days=365)
snapshot.signed.meta={'targets.json':MetaFile.from_data(targets.signed.version,(metadata/'targets.json').read_bytes(),['sha256'])}
snapshot.sign(CryptoSigner(serialization.load_pem_private_key(os.environ['PQUA_TUF_SNAPSHOT_KEY'].encode(),password=None)))
root.verify_delegate('snapshot',snapshot);snapshot.to_file(str(metadata/'snapshot.json'))
timestamp.signed.version+=1;timestamp.signed.expires=now+timedelta(days=30)
timestamp.signed.snapshot_meta=MetaFile.from_data(snapshot.signed.version,(metadata/'snapshot.json').read_bytes(),['sha256'])
timestamp.sign(CryptoSigner(serialization.load_pem_private_key(os.environ['PQUA_TUF_TIMESTAMP_KEY'].encode(),password=None)))
root.verify_delegate('timestamp',timestamp);timestamp.to_file(str(metadata/'timestamp.json'))
for args in [['config','user.name','Pawquanta Maintenance'],['config','user.email','maintenance@users.noreply.github.com'],
             ['add','metadata/snapshot.json','metadata/timestamp.json'],['commit','-m','Renew approved update metadata freshness'],['push','origin','HEAD:wallet-updates']]:
    subprocess.run(['git','-C',str(feed),*args],check=True)
