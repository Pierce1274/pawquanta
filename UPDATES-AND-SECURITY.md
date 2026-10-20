# Updates and network security — v0.5.0

## Automatic application updates

Version 0.4.2 introduces publisher-approved updates using The Update Framework
(TUF). Older wallets need one manual upgrade to this version. There is no way
to remotely add an updater to an older installed wallet.

The visible **Automatically install publisher-approved updates** setting is on
by default and can be disabled. While the wallet is open it checks every fifteen
minutes. A verified update downloads in the background and displays a 30-second
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

A valid signature identifies the approved publisher; it is not proof that new
code is safe. Automatic updates require trust in the publisher's review.

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


## PDCRM resource management

v0.5.0 adds the Pawquanta Dynamic Compute Resource Manager. Open **PDCRM — CPU + GPU resources** to set CPU worker count (logical processors), CPU duty and GPU duty. CPU and GPU can hash concurrently. Duty settings are budgets for bounded work batches, not guaranteed operating-system utilization. CPU and GPU search disjoint nonce ranges; the wallet coordinator alone verifies and submits winners under the existing cumulative mining quota. No consensus or balance changes are made.

CPU workers start at zero until selected. GPU enablement is still selected separately in the wallet; changing that selection takes effect on the next mining start. Worker counts and duty settings apply live. CPU allocation is limited by available memory, reserving approximately 1 GiB for the host plus 256 MiB per worker; a failed memory query allocates no CPU workers. The status shows allocated/requested workers. This is a conservative estimate, not a guarantee against all memory pressure. An existing GPU performance setting is retained unless PDCRM settings are saved.

Windows CPU hashing requires actual Intel/AMD CPU temperatures from Libre Hardware Monitor. In v0.5.1, current versions are supported through the monitor web server at 127.0.0.1:8085; older WMI providers remain supported. Open CPU temperature setup / check in PDCRM for instructions. Bind the monitor to 127.0.0.1 only, not all interfaces. If unavailable, CPU workers do not hash; an enabled, monitored GPU may continue. The wallet does not install sensor drivers, elevate itself, bypass antivirus or treat ACPI/GPU temperatures as CPU-core temperatures. Installing a hardware monitor is a separate operator decision; use its official project and review its driver requirements. On supported Apple Silicon builds, Apple's system thermal pressure applies to both CPU and GPU. This is not a measured CPU temperature.

Policy limits are deliberately conservative, not inferred manufacturer ratings: CPU pauses at 80°C, resumes at 70°C, and stops work at 85°C with at least 30 seconds cooldown. GPU retains its existing 68/66/75°C thresholds and power limits. Detected heat on either monitored component pauses both hashing paths. CPU heat remains latched until a verified cool reading even if CPU telemetry fails. Unavailable CPU readings prevent CPU work; GPU telemetry/worker failures retain the existing stop latch. Normal cooldown resumes automatically. These controls stop mining, not the computer, and cannot guarantee protection against hardware, firmware or driver failures.

CPU reads have a four-second timeout; no new CPU batch starts when the last successful read is over five seconds old. Individual CPU hashing rounds are bounded to about 0.2 seconds, checked every 256 hashes, with interruptible coordination. This is software monitoring, not a real-time hardware thermal cutoff. Leave the operating system and firmware protections enabled. If temperatures are unavailable, do not interpret that as proof the hardware is cool.

The packaged-wallet checks exercise real spawned CPU processes against a private native chain and prove that a one-atomic-unit reward quota is not exceeded. CPU/GPU scheduling is additionally tested with deterministic worker fixtures. GPU hardware support and physical test limits remain those documented in GPU-MINING.md. CPU sensors on each user's computer must be verified separately.

A private one-off mining schedule can pause work until an explicit UTC deadline. Closing the wallet or an automatic application update preserves that schedule. The Stop mining button cancels a pending scheduled resume; a manual Start overrides it. A running wallet resumes after the deadline and peer synchronization. If the app is closed, a separately configured operating-system task must reopen it; this feature does not turn on a powered-off computer.

Manual CPU mode (v0.5.1) is opt-in in PDCRM and requires confirmation. If CPU readings are unavailable, CPU hashing may continue without CPU temperature protection. Enabling it initially selects one worker at no more than 25% duty; users can adjust resources afterward. Verified overheating and GPU thermal pauses still apply. Missing sensors after observed CPU overheating do not clear its cooling latch.
