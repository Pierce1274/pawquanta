# Pawquanta Core candidate

Status: native development builds and private-node acceptance pass; final release checks remain in progress. Public blockchain installation and owner mining are not armed. The separate Python research network remains unchanged.

Base: Bitcoin Core v30.2, commit `4d7d5f6b79d4c11c47e7a828d81296918fd11d4d`. Upstream MIT copyright/license notices remain intact. Reusing code does not supply Bitcoin's miners, economic value or security.

The candidate replaces the research HTTP/shared-key/account chain with native incremental P2P validation, LevelDB chain/UTXO storage, descriptor wallets, secp256k1 signatures, SHA256d proof of work and SegWit/Taproot validation. Existing research wallets, signatures and balances are incompatible and must stay separate.

Candidate public parameters:

- Genesis: zero reward, unspendable OP_RETURN output. Timestamp October 18 2026 at 08:00 PDT. Compiled identity tests verify hash `00000037ccad3f09210835664fce3f8d4ff283e308d8a6cece13e1b4d4d63580`.
- No genesis allocation or imported practice balance. Knowing a genesis in advance does not guarantee a fair first-miner position or prevent others from preparing work.
- Rewards begin at height 1: 40 PQUA, halving every 525,000 rewarded blocks. Integer rounding yields at most 41,999,999.93175 PQUA before any forfeited rewards, below the 42-million ceiling.
- Nominal target 60 seconds; retarget every 120 blocks, fourfold bounds, BIP94 timewarp protection; no special minimum-difficulty exception.
- Public P2P 18731, private RPC 18732, message magic d751a63c, bech32 prefix pqua; no Bitcoin DNS/fixed seeds, assume-valid shortcuts or snapshots.
- All deployed script rules activate at height 1. Bitcoin public testnet/signet selection is disabled. Regression fixtures retain their upstream issuance/genesis for compatibility with upstream adversarial tests, with a separate P2P magic and port; they are never monetary coins.
- Default configuration and data directories use Pawquanta names, preserving existing Bitcoin files.

The initial 24-bit work target is a candidate pending measured MSI mining tests. SHA256d ASICs can overwhelm a small new CPU-mined chain. Host isolation cannot prevent economic/majority-hash attacks. Difficulty economics and externally reachable participation remain launch checks, not established properties.

`core_miner.py` constructs templates including witness commitments, uses one CPU worker and local cookie-authenticated RPC, pins network/genesis and records canonical mining earnings in SQLite. It includes immature coinbase outputs and fees; ordinary transfers and spending do not reset the counter. A final block can claim less than its allowed reward to end exactly at the 1,260,000-PQUA cap. No public miner is armed yet.

Build files and compiler output live on the dedicated D: Linux build image. Windows is not restarted, personal directories are not deleted or shared into the public-node VM, and no existing Bitcoin data is used for tests.

The Windows desktop wallet packages Python/Tk and a hash-pinned native backend. It downloads a hash-pinned official Tor client, connects to an onion peer, creates a private encrypted wallet and backup, and provides Connect/Receive/Send/Start mining/Stop mining buttons. Development packages remain explicitly unarmed. A packaged private-chain test verified payment precision, backup and persistence; that does not establish public-chain readiness.

Upstream historical address/descriptor/PoW vectors were rebased or explicitly pinned to their historical parameter sets, preserving their assertions. Main issuance and PoW have additional independent parameter tests. Miner fee-selection fixtures use an immediate template poll with their frozen mock clock, since a positive wait on a clock that never advances would hang the test.
