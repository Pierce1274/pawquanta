"""CHONK-HASH v1: experimental memory-mixing proof of work. NOT AUDITED."""
import hashlib
import struct

DOMAIN = b'CHONK-HASH-v1\x00'

def digest(header: bytes, nonce: int, memory_kib: int = 256, rounds: int = 1024) -> bytes:
    if not isinstance(header, bytes) or len(header) > 4096:
        raise ValueError('header must be bytes of length <= 4096')
    if not 0 <= nonce < 2**64:
        raise ValueError('nonce out of range')
    if not 16 <= memory_kib <= 65536 or memory_kib % 1:
        raise ValueError('invalid memory_kib')
    if not 1 <= rounds <= 100000:
        raise ValueError('invalid rounds')
    seed = hashlib.sha256(DOMAIN + struct.pack('<I',len(header)) + header + struct.pack('<Q',nonce)).digest()
    count = memory_kib * 1024 // 64
    memory = [b''] * count
    state = seed
    for i in range(count):
        state = hashlib.blake2b(state + seed + struct.pack('<I',i),digest_size=64).digest()
        memory[i] = state
    state = hashlib.blake2b(seed + memory[-1],digest_size=64).digest()
    for i in range(rounds):
        index = int.from_bytes(state[:8], 'little') % count
        state = hashlib.blake2b(state + memory[index] + struct.pack('<I',i),digest_size=64).digest()
        memory[index] = bytes(a ^ b for a,b in zip(memory[index],state))
    return hashlib.sha256(DOMAIN + seed + state + memory[0] + memory[-1]).digest()

def valid_pow(header: bytes, nonce: int, target: int, memory_kib: int=256, rounds: int=1024) -> bool:
    if not 0 < target < 2**256:
        raise ValueError('invalid target')
    return int.from_bytes(digest(header,nonce,memory_kib,rounds),'big') <= target

def mine(header: bytes, target: int, start_nonce: int=0, max_attempts: int=100000, memory_kib: int=256, rounds: int=1024):
    for nonce in range(start_nonce,min(2**64,start_nonce+max_attempts)):
        h = digest(header,nonce,memory_kib,rounds)
        if int.from_bytes(h,'big') <= target:
            return nonce,h.hex()
    return None

if __name__ == '__main__':
    target = (1 << 256) // 8
    result = mine(b'CHONK experimental genesis candidate',target,max_attempts=1000,memory_kib=64,rounds=128)
    print('mined:',result)
    if result:
        assert valid_pow(b'CHONK experimental genesis candidate',result[0],target,64,128)
