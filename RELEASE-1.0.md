# Pawquanta 1.0

This release brings the wallet, miner, diagnostics and recovery tools into one desktop workspace. Existing coins and wallet profiles are retained. No genesis, consensus, reward-schedule or supply change is introduced.

- Unified dashboard with live hash rates, available temperatures, worker allocation, synchronization and session status.
- Connection Doctor with local checks, seed retry and sensor setup.
- Quiet/Balanced profiles and custom PDCRM controls. GPU enablement remains a separate selection.
- Persistent one-session start/duration/reward-ceiling plans. The wallet must remain open and the computer awake.
- Local QR receiving, address book and exact-fee send review before signing.
- Searchable paginated history and CSV export of loaded entries.
- Local block and wallet-transaction explorer.
- Authenticated encrypted backup bundles, integrity verification and recovery into a new wallet folder.
- Installation/update health tools, dark/light themes, text scaling, keyboard shortcuts and reduced motion.

Keep backup bundles and passphrases separately. Recovery refuses existing folders and starts with mining stopped. Existing cumulative reward limits and available reward ledgers are preserved in backup bundles.

Small proof-of-work networks remain vulnerable to majority-hash attacks. The chain monitor is a warning system, not finality. Missing readings are identified; manual CPU mode cannot detect CPU overheating without sensor data. Intel Arc GPU mining is not supported. Windows builds are not publisher-signed; macOS builds are ad-hoc signed and not notarized. Do not disable operating-system security protections.

No marketplace, exchange, escrow, fiat conversion or investment service is included. No guaranteed market value or returns are claimed.
