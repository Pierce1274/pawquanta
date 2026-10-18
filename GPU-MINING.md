# Pawquanta Mainnet GPU mining

This is the existing independent public chain, not a new genesis or a token sale.
Existing balances and the 42-million maximum supply remain unchanged.

Windows: extract the entire ZIP, open Pawquanta-Wallet.exe, Connect, select
"Use NVIDIA / Apple Metal GPU", and Start mining. Stop mining stops hashing.
CPU mode remains available with the checkbox off. No CUDA toolkit or Python
installation is required. A working NVIDIA graphics driver with OpenCL and
nvidia-smi monitoring is required. There is no CUDA backend in this release.

Apple Silicon: the macOS preview uses Apple's native Metal framework. Open
Pawquanta-Wallet.app, Connect, select GPU mode, then Start mining. The app and
its native helper are ad-hoc signed, not Apple-notarized. macOS may refuse to
open them. Do not disable system security. This preview has not been tested on
an M5 Max or an independently operated Mac. Intel Macs and iPhone are not
supported by the Apple Silicon desktop package.

| Hardware/backend | Verification |
| --- | --- |
| GTX 1060, NVIDIA OpenCL, Windows | Physical-device SHA256d comparison, real private-chain block acceptance, quota/restart, packaged executable checks |
| RTX 5090, NVIDIA OpenCL, Windows | Backend target; no physical RTX 5090 test or performance claim |
| Apple Silicon / Metal | Native build and wallet tests when the macOS workflow passes; GPU validation occurs on the user's device before mining |
| M5 Max / Metal | Backend target; no physical M5 Max verification or performance claim |
| AMD, Intel GPU, Linux GPU | Not supported by these packaged GPU modes |

Mining defaults to CPU. GPU is opt-in and replaces the CPU hashing worker.
Both modes use the same durable mining-reward quota, wallet and network rules.
The owner's existing 1,260,000 PQUA limit is not increased by GPU support.

## Conservative watchdog

The GPU worker is a separate, bounded process with no wallet password or RPC
cookie. Every start compares actual GPU SHA256d hashes to CPU hashes; each
winning header is checked again on CPU before submission.

GPU work runs in small batches with at least nine times as much idle time as
measured batch wall time (at most 10% compute duty cycle, not a promise about
the GPU's global utilization). NVIDIA telemetry is sampled at least once per
second during hashing. Pause at 68 C or 65% of the reported enforced power
limit; resume after temperature falls to 62 C and power is below the pause
threshold. Stop at 75 C or 85% of that limit. If a mobile driver does not
report a limit, conservative approximately 50 W pause / 65 W stop ceilings
apply. Missing temperature or power telemetry stops mining.

Apple's supported system thermal state is used instead of invented temperature
readings: nominal permits mining, fair pauses, serious or critical stops. Apple
thermal status describes the system, not a precise GPU temperature or wattage.

Sensor faults, worker failures and hard safety trips latch a GPU-SAFETY-STOP
file beside the mining STOP file. Mining stays stopped until the user checks
cooling and deliberately clears that file. A hung worker is terminated after
the short job timeout; this does not reset the graphics driver. No mining
software can guarantee protection from driver, firmware or hardware faults.

The watchdog reduces load and allows normal hardware cooling. It does not
control fans, overclock, undervolt, raise power limits, install a driver, or
turn off antivirus. Keep vents clear and keep the laptop on a hard surface.

New rewards mature after 100 blocks. Mining consumes electricity, finding a
block is not guaranteed, and PQUA has no established market value.
