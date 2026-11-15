# Preparation-time validation

Date: 13 November 2026.

## Passed in the authoring environment

- Nine Python unittest cases for normal, weak replay, wrong-job, expiry, future timestamp, nonfinite dose, dose bound, duplicate ID and busy-state decisions.
- Python source compilation (syntax check) for the supplied scripts.
- Source/API review against the NS-3 TapBridge/CSMA documentation, OpenPLC v3 Modbus mapping, aiocoap examples and pinned PyModbus client documentation.

## Not completed here

- Linux shell execution: WSL access was denied; the available Git Bash runtime also could not start under the environment restrictions.
- Python dependency installation: package-server DNS resolution failed. The package-install error was environmental and does not establish whether a package is unavailable.
- NS-3 C++ compilation and TAP connectivity.
- OpenPLC Docker build, Structured Text compilation and runtime scan verification.
- Full CoAP → NS-3 → Modbus → PLC → simulated-process execution.
- Actual PCAP, process plots or measured experimental results.

No example measurements or fabricated successful-run logs are included. README predictions are acceptance targets. Run its checkpoints in order before treating the package as a validated testbed.
