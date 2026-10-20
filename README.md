# Pawquanta / PQUA

## Pawquanta 1.0 wallet workspace

Version 1.0 adds a unified dashboard, Connection Doctor, Quiet/Balanced mining profiles, one-session mining schedules, exact-fee send review, receiving-address QR codes, a local address book, searchable paginated history with CSV export, a local block/wallet-transaction explorer, encrypted backup bundles, separate-folder recovery, installation health checks, themes, text scaling and reduced-motion startup.

Mining schedules require the wallet open and the computer awake. Missed sessions do not mine retroactively. CSV export covers loaded history pages. The explorer reads your own node and does not send searches to an external website.

Backup bundles encrypt the native wallet backup, recovery password, receiving address, saved preferences and available mining reward ledger. Keep the bundle and its passphrase separately. Restoring requires a new folder and starts with mining stopped. Integrity authentication is distinct from native-wallet recovery verification.

There is no marketplace, exchange, escrow, fiat conversion or platform custody in this release. Network consensus, genesis, balances and reward rules are unchanged. Pawquanta remains experimental and vulnerable to majority-hash attacks; release 1.0 is not an independent security audit.

Independent, experimental public blockchain software. The release page states deployment status; a countdown or repository alone does not certify a launched network.

## Wallet and miner downloads

1. Open [the mainnet release](https://github.com/Pierce1274/pawquanta/releases/tag/mainnet-v1.0.0) and choose the Windows or Apple Silicon Mac package.
2. Extract the entire ZIP into a folder you can write to. Open **Pawquanta-Wallet.exe** on Windows or **Pawquanta-Wallet.app** on Mac.
3. Click **Connect**. The verified network connection downloads automatically. No Python installation or terminal commands are needed.
4. Use **Receive / copy address**, **Send coins**, **Start mining**, or **Stop mining**.
5. Use **Show backup folder** and privately copy your encrypted backup and recovery password to separate storage. Never upload or share your wallet folder.

Windows packages are unsigned; Mac packages are ad-hoc signed and not notarized. Compare downloads with the release's **SHA256SUMS**. CPU mining and optional NVIDIA/Apple Metal modes are available; Apple GPU support is a preview. Mining does not guarantee income. Rewards mature after 100 blocks.

Version 0.4.2 introduces automatic publisher-approved updates. Older installations need one manual upgrade. Updates check every fifteen minutes while the wallet is open and can be disabled in the wallet. Daily signed-metadata maintenance runs automatically. See [Updates and security](UPDATES-AND-SECURITY.md).

The wallet pauses outgoing payments if previously observed chain history changes and requires inputs with twelve confirmations. These safeguards do not prevent majority-hash attacks. Independent mining power is still essential.

## PDCRM compute resources

v0.5.0 adds in-app CPU worker and CPU/GPU duty controls with simultaneous hashing under one reward limit. Open **PDCRM — CPU + GPU resources**. Windows CPU mining requires a working CPU-temperature provider (local HTTP for current Libre Hardware Monitor, or legacy WMI); missing sensors pause CPU hashing. Supported Apple Silicon builds use system thermal pressure. The app uses conservative limits and does not claim to discover a universally safe temperature. See [PDCRM safety and requirements](UPDATES-AND-SECURITY.md#pdcrm-resource-management).

## The network

The maximum supply is below 42 million PQUA after integer rounding. It is issued over time; it is not allocated at launch. Genesis has no allocation. Rewards start at block 1 with 40 PQUA and halve every 525,000 rewarded blocks. The nominal block target is 60 seconds, with a 120-block difficulty interval.

Each miner runs an independent validating node and wallet. The initial public seed uses an onion service, so the Windows app establishes its own Tor connection automatically. The initial seed remains a single point of availability until additional node operators join. This software does not inherit Bitcoin's hash power, operators, economic value or security. SHA256d ASICs can overwhelm a small CPU-mined chain. No independent security audit or established market value is claimed.

The founder's client has a voluntary stop limit of 1,260,000 PQUA in canonical mining rewards, including immature rewards and fees. That limit does not restrict anyone else's mining or guarantee decentralized hash power. Published source and genesis do not guarantee anyone first-miner status.

## Source and verification

- `core/`: Bitcoin Core v30.2-derived native node, wallet, validation and adversarial tests; upstream MIT notices are preserved.
- `core_wallet.py`, `core_runtime.py`, `core_tor.py`: desktop interface, encrypted local wallet, verified transport download.
- `core_miner.py`: one-worker miner with durable reward accounting and a personal stop limit.
- `core-tools/`: real-node regression acceptance and an explicitly private launch-parameter simulation.
- GitHub Actions contains native builds and tests. Release notes identify the exact native and desktop source commits used by the published packages.

The old Python research edition and its practice balances are separate. See [RESEARCH-README.md](RESEARCH-README.md). Do not use `pawquanta.py` or the research-v0.1.0 practice miner to join this public chain; practice coins do not transfer.

The desktop wallet opens with a short animated Pawquanta splash. Select Open wallet or press Escape to skip it. Set PAWQUANTA_REDUCED_MOTION=1 for motion-free startup. The reveal bar is decorative startup animation, not blockchain synchronization progress.
