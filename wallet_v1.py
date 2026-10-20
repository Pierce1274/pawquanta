"""Pawquanta 1.0 wallet utilities. SPDX-License-Identifier: MIT"""
import base64,csv,hashlib,json,os,sqlite3,time,uuid
from decimal import Decimal,InvalidOperation
from pathlib import Path
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from core_runtime import MAIN_GENESIS,private_directory
UNIT=100_000_000
BACKUP_MAGIC=b'PQUABK1\0'
MAX_BACKUP=128*1024*1024


def atomic_json(path,value):
    path=Path(path);temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temporary.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2);f.flush();os.fsync(f.fileno())
    temporary.replace(path)


def prepare_profile(profile):
    profile=Path(profile);marker=profile/'.pawquanta-runtime.json';identity={'genesis':MAIN_GENESIS,'development':False,'schema':1}
    if profile.exists() and any(profile.iterdir()) and not marker.exists():raise ValueError('Unrecognized wallet folder; existing files preserved')
    if marker.exists() and json.loads(marker.read_text())!=identity:raise ValueError('Wallet folder network mismatch')
    private_directory(profile)
    if not marker.exists():atomic_json(marker,identity)


def preferences(profile):
    path=Path(profile)/'wallet-ui.json'
    try:value=json.loads(path.read_text()) if path.exists() else {}
    except (OSError,ValueError):value={}
    if not isinstance(value,dict):value={}
    return {'reduced_motion':value.get('reduced_motion') is True,'theme':'light' if value.get('theme')=='light' else 'dark','text_scale':value.get('text_scale') if value.get('text_scale') in (100,120,140) else 100}


def address_book(profile):
    path=Path(profile)/'address-book.json'
    return json.loads(path.read_text()) if path.exists() else []


def save_contact(profile,label,address,rpc):
    label=label.strip()
    if not label or len(label)>60 or not rpc('validateaddress',address).get('isvalid'):raise ValueError('Enter a label and a valid Pawquanta address')
    rows=[r for r in address_book(profile) if r['address']!=address];rows.append({'label':label,'address':address})
    if len(rows)>500:raise ValueError('Address book is limited to 500 contacts')
    atomic_json(Path(profile)/'address-book.json',rows)


def amount_units(text):
    try:
        value=Decimal(str(text));scaled=value*UNIT
        if not value.is_finite() or not 0<value<=42_000_000 or scaled!=scaled.to_integral_value():raise ValueError()
        return int(scaled)
    except (InvalidOperation,ValueError):raise ValueError('Enter a positive PQUA amount with at most eight decimal places')


def prepare_send(runtime,guard,address,amount):
    guard.require_payments(runtime.rpc)
    info=runtime.rpc('validateaddress',address)
    if not info.get('isvalid'):raise ValueError('This is not a valid Pawquanta address')
    units=amount_units(amount)
    funded=runtime.wallet('walletcreatefundedpsbt',[],[{address:format(Decimal(units)/UNIT,'.8f')}],0,{'add_inputs':True,'include_unsafe':False,'minconf':12},True)
    return {'psbt':funded['psbt'],'fee':str(funded['fee']),'address':address,'units':units,'script':info['scriptPubKey'],'created':time.time()}


def confirm_send(runtime,guard,profile,quote):
    if not 0<=time.time()-quote['created']<=180:raise ValueError('Fee quote expired. Review a fresh transaction.')
    guard.require_payments(runtime.rpc)
    name=runtime.wallet('getwalletinfo')['walletname']
    if name not in ('wallet','owner'):raise ValueError('Unexpected wallet identity')
    password=(Path(profile)/(name+'-recovery-password.txt')).read_text().strip()
    runtime.wallet('walletpassphrase',password,30)
    try:
        signed=runtime.wallet('walletprocesspsbt',quote['psbt']);final=runtime.rpc('finalizepsbt',signed['psbt'])
        if not final.get('complete'):raise ValueError('Transaction signing incomplete')
        decoded=runtime.rpc('decoderawtransaction',final['hex'])
        if not any(v['scriptPubKey']['hex']==quote['script'] and Decimal(str(v['value']))*UNIT==quote['units'] for v in decoded['vout']):raise ValueError('Prepared recipient or amount changed')
        return runtime.rpc('sendrawtransaction',final['hex'])
    finally:runtime.wallet('walletlock')


def export_history(file,rows):
    def cell(value):
        s=str(value if value is not None else '')
        return "'"+s if s.startswith(('=','+','-','@','\t','\r')) else s
    with Path(file).open('x',newline='',encoding='utf-8-sig') as f:
        writer=csv.writer(f);writer.writerow(['UTC time','Category','Amount PQUA','Fee PQUA','Confirmations','Address','Label','Transaction ID'])
        for row in rows:writer.writerow([time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(row.get('time',0))),cell(row.get('category')),str(row.get('amount',0)),str(row.get('fee',0)),row.get('confirmations',0),cell(row.get('address')),cell(row.get('label')),row.get('txid','')])


def _key(password,salt):
    if len(password)<12:raise ValueError('Use a backup passphrase of at least 12 characters')
    return Scrypt(salt=salt,length=32,n=32768,r=8,p=1).derive(password.encode('utf-8'))


def make_backup(runtime,profile,password,destination):
    profile=Path(profile);destination=Path(destination)
    if destination.exists():raise ValueError('Choose a new backup filename; existing files are preserved')
    temporary=profile/('backup-stage-'+uuid.uuid4().hex+'.dat')
    try:
        runtime.wallet('backupwallet',str(temporary))
        wallet=temporary.read_bytes()
        if len(wallet)>MAX_BACKUP//2:raise ValueError('Wallet backup is too large for this bundle format')
        name=runtime.wallet('getwalletinfo')['walletname']
        if name not in ('wallet','owner'):raise ValueError('Unexpected wallet identity')
        secret=(profile/(name+'-recovery-password.txt')).read_text().strip()
        address=(profile/(name+'-receiving-address.txt')).read_text().strip()
        body={'schema':1,'genesis':runtime.genesis,'walletname':name,'created':time.time(),'address':address,'password':secret,'wallet':base64.b64encode(wallet).decode(),'sha256':hashlib.sha256(wallet).hexdigest(),'files':{}}
        for filename in ('mining-preferences.json','pdcrm.json','wallet-ui.json','address-book.json'):
            if (profile/filename).exists():body['files'][filename]=base64.b64encode((profile/filename).read_bytes()).decode()
        ledger=profile/'mining-rewards.sqlite'
        if ledger.exists():
            stage=profile/('backup-ledger-'+uuid.uuid4().hex+'.sqlite')
            try:
                source=sqlite3.connect('file:'+ledger.as_posix()+'?mode=ro',uri=True);target=sqlite3.connect(stage)
                try:source.backup(target)
                finally:target.close();source.close()
                body['files']['mining-rewards.sqlite']=base64.b64encode(stage.read_bytes()).decode()
            finally:stage.unlink(missing_ok=True)
        salt=os.urandom(16);nonce=os.urandom(12);raw=json.dumps(body).encode()
        if len(raw)>MAX_BACKUP-64:raise ValueError('Backup exceeds size limit')
        encrypted=AESGCM(_key(password,salt)).encrypt(nonce,raw,BACKUP_MAGIC)
        with destination.open('xb') as f:f.write(BACKUP_MAGIC+salt+nonce+encrypted);f.flush();os.fsync(f.fileno())
        # Verify the exact on-disk bundle before reporting success.
        return read_backup(destination,password,genesis=runtime.genesis)
    finally:temporary.unlink(missing_ok=True)


def read_backup(file,password,genesis=MAIN_GENESIS):
    file=Path(file)
    if file.stat().st_size>MAX_BACKUP:raise ValueError('Backup exceeds size limit')
    raw=file.read_bytes()
    if raw[:8]!=BACKUP_MAGIC or len(raw)<52:raise ValueError('Not a Pawquanta encrypted backup bundle')
    body=json.loads(AESGCM(_key(password,raw[8:24])).decrypt(raw[24:36],raw[36:],BACKUP_MAGIC))
    if body.get('schema')!=1 or body.get('genesis')!=genesis or body.get('walletname') not in ('wallet','owner'):raise ValueError('Backup network or format does not match')
    data=base64.b64decode(body['wallet'],validate=True)
    if hashlib.sha256(data).hexdigest()!=body['sha256'] or not body.get('password') or not body.get('address'):raise ValueError('Backup integrity check failed')
    if set(body.get('files',{}))-{'mining-preferences.json','pdcrm.json','wallet-ui.json','address-book.json','mining-rewards.sqlite'}:raise ValueError('Unexpected backup member')
    for data in body.get('files',{}).values():base64.b64decode(data,validate=True)
    return body


def restore_backup(body,destination,development=False):
    destination=Path(destination)
    if destination.exists():raise ValueError('Restore requires a brand-new folder; existing files were preserved')
    private_directory(destination)
    identity={'genesis':body['genesis'],'development':development,'schema':1}
    atomic_json(destination/'.pawquanta-runtime.json',identity)
    atomic_json(destination/'network.json',{'genesis':body['genesis'],'chain':'regtest' if development else 'main'})
    name=body['walletname'];node=destination/'node'/('regtest' if development else '')/'wallets'/name;node.mkdir(parents=True)
    (node/'wallet.dat').write_bytes(base64.b64decode(body['wallet'],validate=True))
    (destination/(name+'-recovery-password.txt')).write_text(body['password']+'\n')
    (destination/(name+'-receiving-address.txt')).write_text(body['address']+'\n')
    for filename,data in body.get('files',{}).items():(destination/filename).write_bytes(base64.b64decode(data,validate=True))
    atomic_json(destination/'restored-wallet.json',{'walletname':name})
    (destination/'STOP-MINING').touch()
    return destination


def diagnosis(snapshot,compute,worker_alive,stop,guard=None):
    rows=[]
    if not snapshot:return [('Connection','Not connected','Connect the wallet; Tor setup and synchronization must finish first.')]
    rows.append(('Network',f"{snapshot['peers']} peers",'Retry public seed' if not snapshot['peers'] else 'Connected through your node'))
    rows.append(('Synchronization',f"{snapshot['height']} / {snapshot.get('headers',snapshot['height'])}",'Wait for headers and blocks to match' if snapshot['synchronizing'] else 'Up to date'))
    phase=compute.get('cpu',{}).get('phase','unknown')
    rows.append(('CPU',phase,'Open temperature setup or explicitly choose manual mode' if phase=='sensor_unavailable' else 'Manual mode has no CPU temperature protection when readings are missing' if phase=='manual' else 'Review PDCRM worker and duty settings'))
    rows.append(('Mining','Running' if worker_alive and not stop else 'Stopped','Start mining to resume; a schedule may also keep mining stopped'))
    if guard and guard.get('halted'):rows.append(('Payments','Paused',guard.get('reason','Review chain warning')))
    return rows


def mining_profile(name,logical):
    if name=='Quiet':return {'cpu_workers':min(1,logical),'cpu_duty':.25,'gpu_duty':.15,'manual_cpu':False}
    if name=='Balanced':return {'cpu_workers':min(max(1,logical//2),4),'cpu_duty':.5,'gpu_duty':.3,'manual_cpu':False}
    raise ValueError('Choose Quiet or Balanced, or adjust Custom settings in PDCRM')
