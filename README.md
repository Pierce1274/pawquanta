# Pawquanta / PQUA — Research Edition

Working standalone blockchain software for local experiments. **Not a launched public mainnet. Test coins have no monetary value.**

## Easiest way: Windows desktop app

1. Open **Releases** on this repository and download `Pawquanta-Research-Windows-x64.zip`.
2. Extract the entire ZIP into a folder you can write to.
3. Open `Pawquanta-Research.exe`. No separate Python installation or package commands are needed.
4. Click **Create wallet**, choose and remember a password, then click **Mine 4 blocks**.
5. Click **Open explorer** to see your chain. **Stop** stops mining between blocks.

Your wallet and chain live in `Pawquanta-data` beside the app. Back up `wallet.pem` and retain its password separately. There is no password reset. Newly mined rewards need three more blocks before spending. Each mining click runs a bounded four-block batch. This app opens only a loopback listener, not an internet port.

**Each copy starts its own local practice network. Separate downloads do not automatically join one shared public chain or share balances.** There is no official public seed, mainnet launch, exchange, sale, or established PQUA price in this release. The graphical app intentionally does not ask you to handle node admission keys.

The Windows build is unsigned. Checksums and the source are provided for inspection. Do not disable antivirus or other security protections to run it. Windows x64 is the only packaged platform currently verified; phone, macOS and Linux packaged miners have not been provided.

## Source, verification and developers

Python 3.11+ is required when running from source:

```text
python -m venv .venv
```

On Windows:

```text
.venv\Scripts\python -m pip install -r requirements-lock.txt
.venv\Scripts\python -m unittest -v test_pawquanta
.venv\Scripts\python easy_miner.py
```

On Linux/macOS, use `.venv/bin/python` instead. A working Tk installation is required for the source GUI; server and tests do not need Tk. These source paths are for developers; the packaged Windows app bundles its runtime.

The source contains an account-based PoW blockchain, Ed25519 signed payments, encrypted wallets, fees, maturity, work-based fork selection, reorg handling, private peer sync, deterministic vectors and property/adversarial tests. The original CHONK-HASH and mascot were supplied with the research kit.

## Limits and security

- Short-lived research protocol: 1,999 mined blocks / 8 MiB chain limit; full-chain sync and replay.
- Experimental 16-KiB, 32-round CHONK-HASH. No ASIC-resistance, GPU-resistance, novelty or security proof.
- Node transport uses Python's development HTTP server. It is not hardened for public internet exposure.
- Private peer endpoints use a shared admission secret. Public participation requires a different networking release.
- No independent audit, production wallet recovery, peer discovery, long-term storage engine or open-network stress validation.
- Supply uses integer atomic units, no genesis allocation, 40 initial PQUA and 525,000-block halvings. The theoretical lifetime subsidy is 41,999,999.93175 PQUA, below the 42-million ceiling. This network cannot reach its later eras because of its research lifetime limit.

Do not forward these node ports to the internet or use the code for real funds. A VM does not turn this prototype into production consensus. Bitcoin-level security, adoption and profitability are not claimed.

## Build the Windows app yourself

Install PyInstaller in the development environment, then from the repository root:

```text
python -m PyInstaller --noconfirm --onedir --windowed --name Pawquanta-Research --paths Pawquanta-research --add-data "Pawquanta-research/assets/mascot.jpg;Pawquanta-research/assets" --add-data "countdown.html;." easy_miner.py
```

Run `dist/Pawquanta-Research/Pawquanta-Research.exe --self-test` to exercise encrypted wallets, mining, a signed payment and persistence. It writes `self-test-result.json` beside the executable. Keep every file under `_internal` alongside the EXE when distributing. The release ZIP includes third-party license notices.
