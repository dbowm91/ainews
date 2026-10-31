# E3 — Linux aarch64 Packaging and Upstream Release Qualification

**Status:** UPSTREAM RELEASE GATE CLOSED by EggFetch 0.3.0; unsigned-tag provenance is recorded as an adoption caveat for E4.
**Priority:** P1 adoption blocker.
**Parent:** [EggFetch HTTP transport pilot](eggfetch_transport_pilot_20261030.md).
**Next:** E1 and E2 may proceed in parallel. E4 depends on E1–E3.

## Objective

Deliver a reproducible EggFetch artifact for AInews's supported targets and qualify the exact upstream revision that contains the bridge, timeout fix, and URL compatibility required by AInews.

## Supported pilot matrix

Run CPython 3.12 on:

- Linux x86_64
- Linux aarch64
- macOS arm64 (Apple Silicon)

Windows deployment uses WSL/Linux. Intel macOS and native Windows are not AInews pilot targets. The earlier x86_64 Python platform tag on this Apple Silicon host does not add an Intel Mac requirement. EggFetch 0.2.2 has CPython 3.12 wheels for Linux x86_64 and macOS arm64, but no Linux aarch64 wheel.

## Implementation scope

1. Preferred: add manylinux aarch64 wheel builds to EggFetch's release matrix. Use native Linux aarch64 CI for installation/import/request smoke, or document and validate any cross-build limitations with a native execution gate before publication.
2. If a wheel is not feasible, provide a reproducible source-build recipe using a pinned Rust toolchain and maturin. Validate it in AInews's actual Docker builder and installer/build workflows; keep Rust tooling out of the runtime image. A developer-only local build does not qualify.
3. Verify wheel tags, Python ABI, glibc baseline, artifact provenance, and installation from a clean frozen environment.
4. Integrate the `URL.copy_with(raw_path=...)` compatibility patch with focused coverage and an OpenAI 2.29.0 downstream fixture.
5. Resolve EggFetch required-suite instability observed during the pilot. Repeated Tier 1 runs failed in the benchmark origin-form/repeated-GET test; a later isolated rerun also failed. A proxy reconnect test failed once and passed alone. Diagnose root causes and make the project's required upstream suite repeatable. This is EggFetch's own test-suite gate; it does not add proxy-based AInews qualification.
6. Run the EggFetch verification policy on a clean frozen exact commit SHA. Any code/test change invalidates qualification for a previous SHA; record the SHA and commands alongside artifact provenance.

## Acceptance criteria

- Frozen install, import, minimal request, and packaging smoke pass on native CPython 3.12 for all three target platforms.
- Linux aarch64 works from a published wheel or from a validated, reproducible source build wired into supported AInews build paths.
- EggFetch's required check suite is clean and repeatable on the candidate SHA, including the previously unstable cases.
- The candidate contains E1/E2 fixes and URL compatibility coverage; the released artifact is immutable and provenance is recorded.
- `darwin x86_64` in AInews `uv.required-environments` is reconciled separately if the metadata is being normalized; it is not a reason to support Intel macOS.

## Stop conditions

If no supported Linux aarch64 install path can be produced or required upstream checks remain flaky, keep adoption deferred. Do not add an unpinned compiler installation to AInews or claim support from a one-off developer build.

## Implementation and evidence — 2026-10-30

- Added CPython 3.10–3.15 Linux aarch64 rows to EggFetch's manual PyPI wheel
  workflow, built and smoke-tested on native `ubuntu-24.04-arm` runners. Updated
  wheel-coverage validation and current release documentation from 18 to 24
  wheels. GitHub documents this runner for public and private repositories;
  see [GitHub-hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
- Apple Silicon remains the only AInews macOS target. No Intel macOS matrix
  was added. Windows remains outside the AInews target matrix (WSL/Linux is
  used).
- Local qualification on the current uncommitted worktree: Python bridge, SDK,
  and URL suites passed (115 tests); `cargo clippy --workspace --exclude
  eggfetch-python --all-targets --all-features -- -D warnings` and formatting
  checks passed. The broad Rust workspace suite passed with `eggfetch-bench`
  excluded. The full workspace run stopped at the known
  `bench_proxy::tests::forwards_complete_origin_form_requests_and_repeated_gets`
  connection-reset/incomplete-message flake. A separate focused rerun failed
  again. Its baseline incidence was already measured at 5/16 runs on the true
  baseline versus 4/16 on the previous pilot change; no root cause or reliable
  fix has been established. A body-wrapper transparency correction was made
  and the timeout/native body suites still pass (15 and 16 tests respectively),
  but the proxy fixture remains unstable.
- A synthetic 24-wheel filename matrix passed the updated coverage checker.
  This validates matrix arithmetic only; no native ARM runner or release
  artifact was available locally.
- EggFetch 0.3.0 is published from executable SHA
  `6093cc7aa0961194f096cbf2f92c3fc057671a34`, with 24 wheels plus an sdist.
  The release workflow's supported-platform wheel smoke tests, including
  native macOS arm64 and Linux aarch64, passed; PyPI publication and assembled
  release-set validation completed. See the upstream
  [0.3.0 publication closure](https://github.com/eggstack/eggfetch/releases/tag/v0.3.0).
- The release tag is annotated but unsigned and carries environment tagger
  metadata. E4 must record whether the locked PyPI artifact hashes and release
  evidence are acceptable for this adoption. Signed tags remain the
  requirement for future releases.
- The prior benchmark proxy fixture failure was resolved before release; the
  final release workflow completed successfully.
