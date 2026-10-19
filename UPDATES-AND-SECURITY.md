# Updates and network security — v0.4.2

## Automatic application updates

Version 0.4.2 introduces publisher-approved updates using The Update Framework
(TUF). Older wallets need one manual upgrade to this version. There is no way
to remotely add an updater to an older installed wallet.

The visible **Automatically install publisher-approved updates** setting is on
by default and can be disabled. While the wallet is open it checks every six
hours. A verified update downloads in the background and displays a 30-second
restart notice. Uncheck automatic updates to defer installation.

An update waits for an active payment interaction to finish, stops mining and
closes the local node cleanly. It installs into a separate version directory,
reopens the same wallet directory, reconnects, and resumes previously active
mining after synchronization with its saved cumulative reward budget. It does
not create a new wallet or reset the reward ledger. A failed installation
leaves the old application and wallet files in place and reconnects the old
application. Existing application folders are retained.

TUF signatures, expiration, metadata versions, package sizes and SHA-256 hashes
are checked. Archive traversal, duplicate paths, unsafe symlinks, reserved
filenames and oversized archives are rejected. Bootstrap trust comes from the
root metadata bundled with the initial application. Protect that initial
download and compare its published checksum.

Only an approved release can change software. Scheduled maintenance can renew
freshness metadata using limited online keys, but cannot sign a new targets
list. Root and release-approval private keys are not shipped with the app or
stored in GitHub Actions. Protocol changes require a separate manual upgrade;
the automatic channel rejects them.

Windows builds are not publisher-signed, and macOS builds are ad-hoc signed
without Apple notarization. Do not disable operating-system security to run
them. TUF protects the update channel after bootstrap; it does not replace
operating-system signing or an independent code audit.

## Majority-hash attacks remain possible

Pawquanta remains a small SHA-256d proof-of-work network. A miner with enough
hashpower can build a competing chain, reorganize history and attempt to
double-spend its own payments. Wallet software cannot eliminate that threat
without additional mining security or a different consensus trust model.

The wallet remembers recently observed block hashes and pauses outgoing
payments when previously observed history changes. The warning persists after
restart. **Review chain warning** permits explicit acknowledgement after an
independent check. The monitor cannot authenticate history predating its first
observation or guarantee detection of every hostile branch. It is a local
alarm, not a consensus checkpoint or finality mechanism.

Outgoing payments require inputs with at least 12 confirmations and exclude
unsafe inputs. Mining rewards still mature after 100 blocks. No confirmation
count guarantees safety against a sustained majority attacker. Merchants
should not treat this experimental network as a secure settlement system for
valuable goods or services.

The update changes no genesis block, balances, reward schedule or supply rules.
It adds no authority capable of declaring finalized blocks. Mining optimizations,
cooling recovery and reconnect fixes are also included in this release.

## Availability and maintenance

Approved metadata freshness is renewed daily through GitHub Actions. If that
service or the network is unavailable, the wallet keeps operating with its
installed application and refuses unverifiable updates. Approval keys and
metadata have a lifecycle and eventually need operator attention.

The seed still depends on its operator's MSI, internet connection and power.
Local service supervisors and mining cooldown/reconnect logic handle routine
recovery; they cannot recover a powered-off computer or create independent
nodes. Other operators must host reachable nodes for greater availability.

## Approving a future release

Build and test both platform packages, publish them under the intended GitHub
release, then run `build-tools/approve-wallet-release.py approve` with the new
version, an increasing serial, and both package paths. The approval password is
required. Publish only `update-feed/metadata` and `update-feed/targets/channel.json`
to the `wallet-updates` branch. Never publish the protected signing folder.

The release pipeline must update the application VERSION and SERIAL values
alongside the package version. The packaged trust root must remain compatible
with existing clients; rotate roots through TUF's signed root-rotation process.
