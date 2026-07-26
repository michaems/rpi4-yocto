# GitHub Actions CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A GitHub Actions workflow that runs unit tests + config smoke test on every push/PR, and builds the full RPi4 Yocto image (uploading the flashable `.wic.bz2` as an artifact) on manual dispatch or `v*` tags, on the free `ubuntu-24.04` hosted runner.

**Architecture:** One workflow file with two independent jobs (`test`, `build-image`). CI-specific BitBake overrides (`rm_work`, thread caps) are injected by a small tested Python script that writes `project.ci.yml` from `project.yml` using the existing `local_conf_extra` schema key; the build job runs `./build.py --config project.ci.yml`. sstate and downloads are cached via `actions/cache` with always-save semantics so a timed-out cold build resumes on re-run.

**Tech Stack:** GitHub Actions (`actions/checkout@v4`, `actions/cache@v4` restore/save, `actions/upload-artifact@v4`, `actions/setup-python@v5`), Python 3 + PyYAML, pytest, Yocto Scarthgap via the existing `build.py`.

**Spec:** `docs/superpowers/specs/2026-07-26-github-actions-ci-design.md`. One refinement vs the spec: the CI-override step is a tested script file (`scripts/make_ci_config.py`) rather than inline workflow Python — same behavior, but unit-testable, matching the repo's testing culture. The spec's "runner-local copy of project.yml" is realized as `project.ci.yml` (git-ignored, generated on the runner).

## Global Constraints

- Runner: `ubuntu-24.04` (both jobs). Ubuntu 24.04 is PEP 668 externally-managed: the build job must get PyYAML from apt (`python3-yaml`), NOT pip. The test job uses `actions/setup-python`, where pip is fine.
- Committed `project.yml` and `build.py` must NOT change.
- CI overrides injected: `INHERIT += "rm_work"`, `BB_NUMBER_THREADS = "4"`, `PARALLEL_MAKE = "-j 4"` (4-vCPU runner).
- Build job artifact paths: `build/tmp/deploy/images/raspberrypi4-64/*.wic.bz2` and `*.wic.bmap`, `retention-days: 30`.
- Build step timeout 300 min (step-level, NOT job-level, so `if: always()` cache saves still run); job timeout 355 min.
- Commit messages follow the repo's `feat:`/`fix:`/`docs:` convention.
- Work on a feature branch (e.g. `feature/github-actions-ci`), not `main`.

---

### Task 1: CI config generator (`scripts/make_ci_config.py`)

**Files:**
- Create: `scripts/make_ci_config.py`
- Modify: `tests/conftest.py` (add `scripts/` to `sys.path`)
- Modify: `.gitignore` (ignore `project.ci.yml`)
- Test: `tests/test_make_ci_config.py`

**Interfaces:**
- Consumes: `project.yml` schema as validated by `build.load_config` (top-level optional key `local_conf_extra: list[str]`).
- Produces: `make_ci_config(text: str) -> str` — takes project-YAML text, returns YAML text with CI override lines appended to `local_conf_extra`; module constant `CI_LOCAL_CONF: list[str]`; CLI `python3 scripts/make_ci_config.py <src> <dest>`. Task 3's workflow calls the CLI form.

- [ ] **Step 1: Add `scripts/` to the test import path**

In `tests/conftest.py`, replace the whole file with:

```python
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_make_ci_config.py`:

```python
from pathlib import Path

import yaml

import build
import make_ci_config

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_appends_ci_overrides_to_existing_extra():
    src = REPO_ROOT / "project.yml"
    out = make_ci_config.make_ci_config(src.read_text())
    cfg = yaml.safe_load(out)
    extra = cfg["local_conf_extra"]
    assert 'INHERIT += "rm_work"' in extra
    assert 'BB_NUMBER_THREADS = "4"' in extra
    assert 'PARALLEL_MAKE = "-j 4"' in extra


def test_preserves_existing_extra_lines():
    text = (REPO_ROOT / "project.yml").read_text()
    cfg = yaml.safe_load(text)
    cfg["local_conf_extra"] = ['FOO = "bar"']
    out = make_ci_config.make_ci_config(yaml.safe_dump(cfg))
    result = yaml.safe_load(out)["local_conf_extra"]
    assert result[0] == 'FOO = "bar"'
    assert 'INHERIT += "rm_work"' in result


def test_output_still_validates():
    out = make_ci_config.make_ci_config((REPO_ROOT / "project.yml").read_text())
    build.validate_config(yaml.safe_load(out))


def test_everything_else_unchanged():
    src_text = (REPO_ROOT / "project.yml").read_text()
    src = yaml.safe_load(src_text)
    out = yaml.safe_load(make_ci_config.make_ci_config(src_text))
    out.pop("local_conf_extra")
    src.pop("local_conf_extra")
    assert out == src


def test_cli_writes_dest_file(tmp_path):
    dest = tmp_path / "project.ci.yml"
    make_ci_config.main([str(REPO_ROOT / "project.yml"), str(dest)])
    cfg = yaml.safe_load(dest.read_text())
    assert 'INHERIT += "rm_work"' in cfg["local_conf_extra"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_make_ci_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'make_ci_config'`

- [ ] **Step 4: Write the implementation**

Create `scripts/make_ci_config.py`:

```python
#!/usr/bin/env python3
"""Write a CI variant of project.yml with runner-specific local.conf overrides.

Usage: make_ci_config.py <src-yaml> <dest-yaml>

Appends rm_work and 4-vCPU parallelism caps to local_conf_extra so the
Yocto build fits a GitHub-hosted runner. Everything else passes through.
"""

import sys

import yaml

CI_LOCAL_CONF = [
    'INHERIT += "rm_work"',
    'BB_NUMBER_THREADS = "4"',
    'PARALLEL_MAKE = "-j 4"',
]


def make_ci_config(text):
    cfg = yaml.safe_load(text)
    cfg["local_conf_extra"] = (cfg.get("local_conf_extra") or []) + CI_LOCAL_CONF
    return yaml.safe_dump(cfg, sort_keys=False)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        raise SystemExit("usage: make_ci_config.py <src-yaml> <dest-yaml>")
    src, dest = argv
    with open(src, "r", encoding="utf-8") as fh:
        out = make_ci_config(fh.read())
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_make_ci_config.py -v`
Expected: 5 passed

- [ ] **Step 6: Run the whole suite (conftest change must not break anything)**

Run: `python3 -m pytest tests/ -q`
Expected: all pass, no errors

- [ ] **Step 7: Git-ignore the generated file**

Append to `.gitignore` (create the line, keep existing content):

```
project.ci.yml
```

- [ ] **Step 8: Commit**

```bash
git add scripts/make_ci_config.py tests/test_make_ci_config.py tests/conftest.py .gitignore
git commit -m "feat: CI config generator appending rm_work and thread caps"
```

---

### Task 2: Workflow with the `test` job

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `python3 -m pytest tests/`, `./build.py --no-build` (exit 0 on success).
- Produces: workflow `name: CI` with job `test`; Task 3 appends the `build-image` job to this same file, relying on the `on:` block defined here.

- [ ] **Step 1: Write the workflow file**

Create `.github/workflows/ci.yml`:

```yaml
# CI for rpi4-yocto.
#
# - test: unit tests + config-generation smoke test, every push and PR.
# - build-image (added separately): full Yocto image build, manual
#   dispatch or v* tags. If a cold-cache build hits the timeout, just
#   re-run it -- it resumes from the saved sstate cache.

name: CI

on:
  push:
    branches: ['**']
    tags: ['v*']
  pull_request:
  workflow_dispatch:

jobs:
  test:
    if: github.event_name == 'push' || github.event_name == 'pull_request'
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install Python dependencies
        run: pip install pyyaml pytest

      - name: Unit tests
        run: python3 -m pytest tests/ -v

      - name: Config-generation smoke test
        run: ./build.py --no-build
```

- [ ] **Step 2: Validate the YAML parses**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "feat: CI workflow - unit tests and config smoke test on push/PR"
```

---

### Task 3: `build-image` job

**Files:**
- Modify: `.github/workflows/ci.yml` (append the second job)

**Interfaces:**
- Consumes: `scripts/make_ci_config.py` CLI from Task 1; the `on:` block from Task 2.
- Produces: job `build-image` uploading artifact named `rpi4-image`.

- [ ] **Step 1: Append the build job**

Append to `.github/workflows/ci.yml`, inside `jobs:` (same indent level as `test:`):

```yaml
  build-image:
    if: github.event_name == 'workflow_dispatch' || startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-24.04
    timeout-minutes: 355
    steps:
      - uses: actions/checkout@v4

      - name: Free disk space
        run: |
          echo "Before cleanup:" && df -h /
          sudo rm -rf /usr/local/lib/android /usr/share/dotnet /opt/ghc \
            /usr/local/.ghcup /usr/share/swift /opt/hostedtoolcache/CodeQL
          sudo docker image prune --all --force
          echo "After cleanup:" && df -h /

      - name: Install Yocto host dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y --no-install-recommends \
            build-essential chrpath cpio debianutils diffstat file gawk \
            gcc git iputils-ping liblz4-tool locales python3 python3-git \
            python3-jinja2 python3-pexpect python3-pip python3-subunit \
            python3-yaml socat texinfo unzip wget xz-utils zstd
          sudo locale-gen en_US.UTF-8

      - name: Restore sstate cache
        uses: actions/cache/restore@v4
        with:
          path: build/sstate-cache
          key: sstate-${{ hashFiles('project.yml') }}-${{ github.run_id }}
          restore-keys: |
            sstate-${{ hashFiles('project.yml') }}-
            sstate-

      - name: Restore downloads cache
        uses: actions/cache/restore@v4
        with:
          path: build/downloads
          key: downloads-${{ hashFiles('project.yml') }}-${{ github.run_id }}
          restore-keys: |
            downloads-${{ hashFiles('project.yml') }}-
            downloads-

      - name: Generate CI build config
        run: python3 scripts/make_ci_config.py project.yml project.ci.yml

      - name: Build image
        timeout-minutes: 300
        env:
          LANG: en_US.UTF-8
        run: ./build.py --config project.ci.yml

      - name: Upload image artifact
        uses: actions/upload-artifact@v4
        with:
          name: rpi4-image
          path: |
            build/tmp/deploy/images/raspberrypi4-64/*.wic.bz2
            build/tmp/deploy/images/raspberrypi4-64/*.wic.bmap
          retention-days: 30

      - name: Save sstate cache
        if: always()
        uses: actions/cache/save@v4
        with:
          path: build/sstate-cache
          key: sstate-${{ hashFiles('project.yml') }}-${{ github.run_id }}

      - name: Save downloads cache
        if: always()
        uses: actions/cache/save@v4
        with:
          path: build/downloads
          key: downloads-${{ hashFiles('project.yml') }}-${{ github.run_id }}
```

Notes for the implementer (context, not extra steps):
- Cache keys include `github.run_id` so every run saves a fresh cache; `restore-keys` prefix-match picks the most recent previous one. `actions/cache/save` never overwrites an existing key, which is why the key must be unique per run.
- The `Build image` step has its own 300-minute timeout so that when a cold build overruns, the two `if: always()` save steps still get ~55 minutes to upload caches before the job-level 355-minute limit.
- `python3-yaml` from apt (not pip): Ubuntu 24.04 blocks system-pip installs (PEP 668) and `build.py` runs under the system interpreter here.

- [ ] **Step 2: Validate the YAML parses and both jobs exist**

Run:

```bash
python3 - <<'EOF'
import yaml
wf = yaml.safe_load(open('.github/workflows/ci.yml'))
assert set(wf['jobs']) == {'test', 'build-image'}, wf['jobs'].keys()
steps = [s.get('name', s.get('uses')) for s in wf['jobs']['build-image']['steps']]
print('\n'.join(steps))
EOF
```

Expected: prints the 10 step names, ending with `Save downloads cache`; no assertion error.

- [ ] **Step 3: Sanity-check the CI config generator against the real project.yml**

Run: `python3 scripts/make_ci_config.py project.yml /tmp/project.ci.yml && tail -5 /tmp/project.ci.yml`
Expected: last lines show `local_conf_extra:` containing `INHERIT += "rm_work"`, `BB_NUMBER_THREADS = "4"`, `PARALLEL_MAKE = "-j 4"`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "feat: CI full-image build job with disk cleanup and sstate cache"
```

---

### Task 4: README CI section

**Files:**
- Modify: `README.md` (insert a `## CI` section between `## Usage` and `## Flashing`)

**Interfaces:**
- Consumes: job/artifact names from Tasks 2-3 (`test`, `build-image`, artifact `rpi4-image`).
- Produces: user-facing docs only.

- [ ] **Step 1: Add the CI section**

Insert into `README.md` after the `## Usage` section (after the line `\`project.yml\`; edit it and re-run \`./build.py\`.`):

```markdown
## CI

GitHub Actions (`.github/workflows/ci.yml`) runs two jobs:

- **test** — on every push and pull request: unit tests plus a
  `./build.py --no-build` smoke test.
- **build-image** — on manual dispatch (Actions → CI → Run workflow) or
  a `v*` tag: full image build on a hosted runner. The flashable
  `.wic.bz2` + `.bmap` land in the run's `rpi4-image` artifact
  (30-day retention).

The image job frees ~30 GB of preinstalled runner software, builds with
`rm_work`, and caches sstate/downloads between runs. A first (cold-cache)
build takes several hours; if it hits the timeout, re-run the workflow —
it resumes from the saved sstate cache. CI-only BitBake overrides are
injected by `scripts/make_ci_config.py`, which writes a git-ignored
`project.ci.yml`; the committed `project.yml` is untouched.
```

- [ ] **Step 2: Verify the section landed correctly**

Run: `grep -n "^## " README.md`
Expected: `## CI` appears between `## Usage` and `## Flashing`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: CI section - jobs, image artifact, cold-cache re-run note"
```

---

### Task 5: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Full test suite**

Run: `python3 -m pytest tests/ -q`
Expected: all tests pass.

- [ ] **Step 2: Workflow YAML re-check**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Confirm nothing committed touches project.yml or build.py**

Run: `git diff main --stat -- project.yml build.py`
Expected: empty output.

Remaining validation happens on GitHub after the branch is pushed (out of scope for local execution; needs the user):
1. Push the branch → the `test` job must go green.
2. Merge, then Actions → CI → Run workflow → `build-image`. A cold run may time out near 6 h; re-run once — sstate resumes it. Download `rpi4-image` artifact and flash per README.
