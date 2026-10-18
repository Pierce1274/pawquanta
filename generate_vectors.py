"""Public deterministic fixtures. Keys below are public test vectors, never wallets."""
import copy
import json
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import pawquanta as p

key=Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
pub=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
miner=p.address(pub)
chain=[copy.deepcopy(p.GENESIS)]
for h in range(1,6):
    txs=[] if h<5 else [p.sign(key,'pqua_'+'1'*40,10*p.UNIT,0,1000)]
    block={'network':p.NETWORK,'height':h,'previous':p.sha(chain[-1]),'timestamp':h*60,
           'target':p.next_target(chain),'nonce':0,'miner':miner,'transactions':txs}
    while int.from_bytes(p.pow_bytes(block),'big')>block['target']: block['nonce']+=1
    chain.append(block)
state=p.validate(chain,now=300)
vectors={'warning':'PUBLIC TEST VECTOR KEY: bytes(range(32)); never use for funds',
         'genesis_hash':p.sha(p.GENESIS),'chain':chain,'tip':p.sha(chain[-1]),
         'pow_hash':p.pow_bytes(chain[-1]).hex(),'canonical_last_block':p.canonical(chain[-1]).decode(),
         'transaction_id':p.sha(chain[-1]['transactions'][0]),'emission_atomic_units':p.emission_total(),
         'state':state}
Path('vectors.json').write_text(json.dumps(vectors,indent=2))
print('Published deterministic vectors.json')
