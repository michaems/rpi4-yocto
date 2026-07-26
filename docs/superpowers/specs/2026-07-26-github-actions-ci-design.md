# GitHub Actions CI for rpi4-yocto — Design

Date: 2026-07-26
Status: approved approach — single workflow, free hosted runner, sstate cache
via `actions/cache` (approach A).

## Goal

Build the full RPi4 Yocto image (`core-image-full-cmdline`, Scarthgap) in
GitHub Actions on the free `ubuntu-latest` hosted runner, and publish the
flashable `.wic.bz2` (+ `.bmap`) as a workflow artifact. Unit tests and config
generation run as a fast separate job on every push/PR.

## Non-goals

- No self-hosted or paid larger runners.
- No external sstate storage (S3/GHCR). If the 10 GB `actions/cache` limit
  thrashes in practice, that is a follow-up project.
- No kas/container build environment; `build.py` stays the single orchestrator.

## Workflow layout

One file: `.github/workflows/ci.yml`, two jobs.

### Job 1: `test`

- Triggers: `push` (all branches), `pull_request`.
- Runner: `ubuntu-latest`.
- Steps: checkout → setup Python 3 → `pip install pyyaml pytest` →
  `python3 -m pytest tests/` → `./build.py --no-build` as a smoke test.
  Note `--no-build` still clones the upstream layers (poky is ~1 GB), so
  this step costs a couple of minutes of network time on the runner —
  acceptable, and it verifies the fetch + config-generation path end to end.

### Job 2: `build-image`

- Triggers: `workflow_dispatch` (manual button) and `push` on tags `v*`.
- Runner: `ubuntu-latest`, `timeout-minutes: 350` (below the 360 min hard
  kill, so post-steps can still run).
- Steps, in order:
  1. **Free disk space**: remove preinstalled runner software
     (`/usr/local/lib/android`, `/usr/share/dotnet`, `/opt/ghc`,
     `/usr/local/.ghcup`, `/opt/hostedtoolcache/CodeQL`, docker images,
     `/usr/share/swift`) — reclaims roughly 25–35 GB. Print `df -h` before
     and after.
  2. **Install Yocto host dependencies**: the apt list from the README
     (gawk, chrpath, diffstat, zstd, liblz4-tool, …) plus `python3-pip`;
     `pip install pyyaml`.
  3. **Restore caches** (`actions/cache/restore`):
     - `build/sstate-cache` — key `sstate-${{ runner.os }}-<hash of
       project.yml>`, restore-keys fall back to `sstate-${{ runner.os }}-`.
     - `build/downloads` — same scheme with `downloads-` prefix.
  4. **Inject CI overrides into `project.yml`** (small in-place Python step,
     appends to `local_conf_extra`):
     - `INHERIT += "rm_work"` — deletes per-recipe work dirs as the build
       progresses; without it tmp/ alone exceeds the disk.
     - `BB_NUMBER_THREADS = "4"`, `PARALLEL_MAKE = "-j 4"` — match the
       4-vCPU runner instead of oversubscribing.
     - `DL_DIR` and `SSTATE_DIR` are already `build/downloads` and
       `build/sstate-cache` by BitBake default relative to TOPDIR, so no
       override needed.
  5. **Build**: `./build.py`.
  6. **Upload artifact**: `build/tmp/deploy/images/raspberrypi4-64/*.wic.bz2`
     and `*.wic.bmap`, `retention-days: 30`.
  7. **Save caches** (`actions/cache/save` with `if: always()`): so a run
     that hits the timeout still warms the next run's sstate — this is the
     mechanism that lets a cold build that dies at 6 h finish on the second
     attempt.

## Cache strategy and the 10 GB limit

GitHub evicts least-recently-used caches beyond 10 GB per repo. sstate for
this image compresses to roughly 5–8 GB; downloads are of similar order.
Both may not fit together. Decision: both are cached, sstate saved *after*
downloads in step order (more recently touched → evicted last). If eviction
makes rebuilds slow, drop the downloads cache first — sources re-download
faster than they re-compile.

## Error handling

- Cold-build timeout: mitigated by `if: always()` cache save + re-run.
  Documented in the workflow file header comment: "if the first manual run
  times out, just re-run it — it resumes from sstate."
- Disk exhaustion mid-build: `rm_work` plus the cleanup step gives
  ~55–60 GB free for a build that needs ~40–50 GB with rm_work; `df -h`
  printed before the build for post-mortem.
- The `test` job is required to be green independently; `build-image` does
  not depend on it (a manual dispatch should not wait on unrelated pushes).

## Testing

- The `test` job itself is the regression net for `build.py`.
- The CI-override injection step is a ~10-line inline Python script inside
  the workflow; it is exercised on every `build-image` run and validated
  locally once by running the same snippet against `project.yml`.
- Full validation of the workflow: one manual `workflow_dispatch` run
  (accepting a possible timeout + re-run on cold cache).

## Files touched

- `.github/workflows/ci.yml` (new)
- `README.md` — short "CI" section: what runs when, where to download the
  image artifact, note about re-running on cold-cache timeout.

Nothing in `build.py` or `project.yml` changes; CI overrides are applied to
a runner-local copy of `project.yml` at workflow runtime via
`local_conf_extra`, which the schema already supports.
