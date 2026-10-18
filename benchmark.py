"""Small, bounded CPU comparison. Different algorithms/parameters are not equivalent security."""
import hashlib
import json
import platform
import time
from pathlib import Path
import pawquanta as p

def measure(fn, count):
    start=time.perf_counter()
    for i in range(count): fn(i)
    elapsed=time.perf_counter()-start
    return {'iterations':count,'seconds':round(elapsed,6),'hashes_per_second':round(count/elapsed,2)}

results={
    'platform':platform.platform(), 'python':platform.python_version(), 'threads':1,
    'chonk_16KiB_32rounds':measure(lambda i:p.digest(b'PQUA-benchmark',i,16,32),500),
    'sha256':measure(lambda i:hashlib.sha256(b'PQUA-benchmark'+i.to_bytes(8,'little')).digest(),100000),
    'scrypt_N16384_r8_p1_16MiB':measure(lambda i:hashlib.scrypt(b'PQUA-benchmark',salt=i.to_bytes(8,'little'),n=16384,r=8,p=1,dklen=32),5),
    'warning':'CPU implementation comparison only; not equivalent security or evidence of GPU/ASIC resistance.'
}
Path('reports').mkdir(exist_ok=True)
Path('reports/benchmark.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
