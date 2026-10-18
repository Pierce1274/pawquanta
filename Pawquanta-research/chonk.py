"""CHONK experimental local blockchain. NOT FOR REAL FUNDS."""
import argparse, base64, hashlib, json, os, time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

from chonk_hash import digest
DIFFICULTY=1
REWARD=40
HALVING=525000
MEMORY_KIB=16
ROUNDS=32
TARGET=(1 << 256)//16
def reward(height): return REWARD >> (height//HALVING)
def pow_hash(block):
    header={k:v for k,v in block.items() if k!="nonce"}
    return digest(canonical(header),block["nonce"],MEMORY_KIB,ROUNDS).hex()
def valid_pow(block): return int(pow_hash(block),16) <= TARGET
GENESIS={'height':0,'previous':'0'*64,'timestamp':0,'nonce':0,'miner':'GENESIS','transactions':[]}

def canonical(obj): return json.dumps(obj,sort_keys=True,separators=(',',':')).encode()
def sha(obj): return hashlib.sha256(canonical(obj)).hexdigest()
def pubkey(key): return base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode()
def address(pub): return 'chonk_'+hashlib.sha256(base64.b64decode(pub,validate=True)).hexdigest()[:40]
def make_wallet(path):
    if os.path.exists(path): raise FileExistsError('Wallet exists; refusing overwrite')
    key=Ed25519PrivateKey.generate()
    raw=key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as f: json.dump({'private_key':base64.b64encode(raw).decode(),'public_key':pubkey(key),'address':address(pubkey(key))},f,indent=2)
    return address(pubkey(key))
def load_wallet(path):
    with open(path) as f: w=json.load(f)
    key=Ed25519PrivateKey.from_private_bytes(base64.b64decode(w['private_key'],validate=True))
    return key, address(pubkey(key))
def sign_tx(path,to,amount,nonce):
    key,src=load_wallet(path)
    if not isinstance(amount,int) or isinstance(amount,bool) or amount<=0: raise ValueError('amount must be positive integer')
    if not isinstance(nonce,int) or nonce<0: raise ValueError('nonce must be nonnegative')
    tx={'from':src,'to':to,'amount':amount,'nonce':nonce,'public_key':pubkey(key)}
    tx['signature']=base64.b64encode(key.sign(canonical(tx))).decode()
    return tx
def verify_tx(tx):
    try:
        if set(tx)!={'from','to','amount','nonce','public_key','signature'}: return False
        if type(tx['amount']) is not int or tx['amount']<=0 or type(tx['nonce']) is not int or tx['nonce']<0: return False
        if not isinstance(tx['to'],str) or not tx['to'].startswith('chonk_') or len(tx['to'])!=46: return False
        if tx['from']!=address(tx['public_key']): return False
        pub=Ed25519PublicKey.from_public_bytes(base64.b64decode(tx['public_key'],validate=True))
        unsigned={k:v for k,v in tx.items() if k!='signature'}
        pub.verify(base64.b64decode(tx['signature'],validate=True),canonical(unsigned))
        return True
    except (ValueError,TypeError,KeyError,OverflowError): return False
    except Exception: return False

def state(blocks):
    if not isinstance(blocks,list) or not blocks or blocks[0]!=GENESIS: raise ValueError('Bad genesis')
    balances={}; nonces={}
    for height,block in enumerate(blocks[1:],1):
        if not isinstance(block,dict) or set(block)!={'height','previous','timestamp','nonce','miner','transactions'}: raise ValueError('Malformed block')
        if type(block['height']) is not int or block['height']!=height or block['previous']!=sha(blocks[height-1]) or not valid_pow(block): raise ValueError('Invalid proof or linkage')
        if type(block['nonce']) is not int or block['nonce']<0 or type(block['timestamp']) is not int: raise ValueError('Invalid header')
        miner=block['miner']
        if not isinstance(miner,str) or not miner.startswith('chonk_') or len(miner)!=46: raise ValueError('Invalid miner address')
        if not isinstance(block['transactions'],list) or len(block['transactions'])>1000: raise ValueError('Invalid transactions')
        # Reward after transactions: prevents spending the same block's newly minted reward.
        for tx in block['transactions']:
            if not verify_tx(tx): raise ValueError('Invalid signature')
            src=tx['from']
            if tx['nonce']!=nonces.get(src,0) or balances.get(src,0)<tx['amount']: raise ValueError('Invalid nonce or insufficient funds')
            nonces[src]=tx['nonce']+1
            balances[src]-=tx['amount']; balances[tx['to']]=balances.get(tx['to'],0)+tx['amount']
        balances[miner]=balances.get(miner,0)+reward(height)
    return balances,nonces

def mine(blocks,miner,txs=None):
    if not isinstance(miner,str) or not miner.startswith('chonk_') or len(miner)!=46: raise ValueError('Invalid address')
    b={'height':len(blocks),'previous':sha(blocks[-1]),'timestamp':int(time.time()),'nonce':0,'miner':miner,'transactions':txs or []}
    while not valid_pow(b): b['nonce']+=1
    state(blocks+[b]); return b

def main():
    p=argparse.ArgumentParser(description='CHONK integrated experimental local blockchain')
    sub=p.add_subparsers(dest='cmd',required=True)
    w=sub.add_parser('wallet'); w.add_argument('file')
    m=sub.add_parser('mine'); m.add_argument('--chain',default='chonk-chain.json'); m.add_argument('--address',required=True)
    s=sub.add_parser('status'); s.add_argument('--chain',default='chonk-chain.json')
    t=sub.add_parser('transfer'); t.add_argument('--wallet',required=True); t.add_argument('--to',required=True); t.add_argument('--amount',required=True,type=int); t.add_argument('--chain',default='chonk-chain.json')
    a=p.parse_args()
    if a.cmd=='wallet': print('New address:',make_wallet(a.file)); return
    blocks=json.load(open(a.chain)) if os.path.exists(a.chain) else [GENESIS]
    balances,nonces=state(blocks)
    if a.cmd=='status': print(json.dumps({'height':len(blocks)-1,'balances':balances,'next_nonces':nonces,'next_reward':reward(len(blocks))},indent=2)); return
    if a.cmd=='mine': b=mine(blocks,a.address)
    else:
        key,src=load_wallet(a.wallet)
        tx=sign_tx(a.wallet,a.to,a.amount,nonces.get(src,0))
        # Local demonstration: transfer and mining in one command.
        b=mine(blocks,src,[tx])
    blocks.append(b)
    temp=a.chain+'.tmp'
    with open(temp,'w') as f: json.dump(blocks,f,indent=2)
    os.replace(temp,a.chain)
    print('Accepted block',b['height'],'CHONK-HASH',pow_hash(b))
if __name__=='__main__': main()
