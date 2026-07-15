# RPi4 Yocto YAML-Driven Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A repo where `./build.py` reads `project.yml` and produces a bootable Yocto image for Raspberry Pi 4 Model B (64-bit) with user `michaems` (sudo, root locked), static IP 192.168.100.180/24 on eth0, Finnish console keymap, and Terminus console font.

**Architecture:** A single-file Python orchestrator (`build.py`, importable by tests) validates `project.yml`, clones pinned Yocto layers into `layers/`, generates `build/conf/local.conf` + `build/conf/bblayers.conf`, templates a systemd `.network` file and `vconsole.conf` into the committed custom layer `meta-rpi4-custom`, then sources the Yocto env and runs BitBake. The custom layer carries a `systemd-conf` bbappend (static IP + console config) and a `sudo-group-conf` recipe (sudoers drop-in).

**Tech Stack:** Python 3.8+ (stdlib + PyYAML), pytest, openssl (SHA-512 crypt hashing), Yocto Scarthgap 5.0 LTS (poky, meta-raspberrypi, meta-openembedded/meta-oe), BitBake.

**Spec:** `docs/superpowers/specs/2026-07-15-rpi4-yocto-yaml-build-design.md`

## Global Constraints

- Yocto release: `scarthgap` branch for all remote layers (poky, meta-raspberrypi, meta-openembedded).
- `MACHINE = "raspberrypi4-64"`, `DISTRO = "poky"`, image `core-image-full-cmdline`.
- `INIT_MANAGER = "systemd"` — networking via systemd-networkd, DNS via systemd-resolved, console via systemd-vconsole-setup.
- User `michaems`, password `michaems` (plaintext lives ONLY in `project.yml`; only a SHA-512 crypt hash may reach any generated file).
- Root login disabled (`usermod -L root`); never enable `debug-tweaks`.
- Static IP `192.168.100.180`, netmask `255.255.255.0`, gateway `192.168.100.1`, DNS `192.168.100.1`, interface `eth0`.
- Console: `KEYMAP=fi`, `FONT=ter-v16n` in `/etc/vconsole.conf`.
- Custom layer name/collection: `meta-rpi4-custom` / `rpi4-custom`, `LAYERSERIES_COMPAT` = `scarthgap`.
- `layers/` and `build/` are git-ignored; `meta-rpi4-custom/` is committed (including the two templated files with their default content).
- Python: stdlib + PyYAML only at runtime; pytest only for tests. No passlib, no `crypt` module (removed in Python 3.13) — hash via `openssl passwd -6`.
- Host tools assumed present: git, tar, bash, openssl, python3, gcc.

---

### Task 1: Repo scaffolding + config loading and validation

**Files:**
- Create: `.gitignore`
- Create: `project.yml`
- Create: `build.py`
- Create: `tests/conftest.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `load_config(path: pathlib.Path) -> dict` — parses YAML, runs validation, returns the config dict.
- Produces: `validate_config(cfg: dict) -> None` — raises `ConfigError` (subclass of `Exception`) with the offending key name in the message.
- Produces: `ConfigError` exception class.
- Later tasks add more functions to the same `build.py` module.

- [ ] **Step 1: Create `.gitignore`**

```gitignore
layers/
build/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 2: Create `project.yml`**

This is the single source of truth from the spec (the `layers:` sub-key on a repo entry lists which sub-directories of the clone are BitBake layers; absent means the clone root is the layer):

```yaml
name: rpi4-yocto
machine: raspberrypi4-64
image: core-image-full-cmdline
distro: poky

layers:
  - name: poky
    url: https://git.yoctoproject.org/poky
    branch: scarthgap
    layers: [meta, meta-poky, meta-yocto-bsp]
  - name: meta-raspberrypi
    url: https://git.yoctoproject.org/meta-raspberrypi
    branch: scarthgap
  - name: meta-openembedded
    url: https://git.openembedded.org/meta-openembedded
    branch: scarthgap
    layers: [meta-oe]
  - name: meta-rpi4-custom
    path: meta-rpi4-custom

user:
  name: michaems
  password: michaems
  sudo: true

root:
  disable_login: true

network:
  interface: eth0
  address: 192.168.100.180
  netmask: 255.255.255.0
  gateway: 192.168.100.1
  dns: [192.168.100.1]

console:
  keymap: fi
  font: ter-v16n

local_conf_extra: []
```

- [ ] **Step 3: Create `tests/conftest.py`**

Makes `import build` work from the tests directory:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 4: Write the failing tests**

`tests/test_config.py`:

```python
import copy
from pathlib import Path

import pytest

import build

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_load_valid_config():
    cfg = build.load_config(REPO_ROOT / "project.yml")
    assert cfg["machine"] == "raspberrypi4-64"
    assert cfg["image"] == "core-image-full-cmdline"
    assert cfg["user"]["name"] == "michaems"
    assert cfg["network"]["address"] == "192.168.100.180"
    assert cfg["console"]["keymap"] == "fi"


@pytest.fixture
def valid_cfg():
    return build.load_config(REPO_ROOT / "project.yml")


def test_missing_top_level_key_raises(valid_cfg):
    cfg = copy.deepcopy(valid_cfg)
    del cfg["network"]
    with pytest.raises(build.ConfigError, match="network"):
        build.validate_config(cfg)


def test_missing_nested_key_raises(valid_cfg):
    cfg = copy.deepcopy(valid_cfg)
    del cfg["user"]["password"]
    with pytest.raises(build.ConfigError, match="user.password"):
        build.validate_config(cfg)


def test_bad_ip_raises(valid_cfg):
    cfg = copy.deepcopy(valid_cfg)
    cfg["network"]["address"] = "192.168.100.999"
    with pytest.raises(build.ConfigError, match="network.address"):
        build.validate_config(cfg)


def test_bad_netmask_raises(valid_cfg):
    cfg = copy.deepcopy(valid_cfg)
    cfg["network"]["netmask"] = "255.0.255.0"
    with pytest.raises(build.ConfigError, match="network.netmask"):
        build.validate_config(cfg)


def test_bad_username_raises(valid_cfg):
    cfg = copy.deepcopy(valid_cfg)
    cfg["user"]["name"] = "9bad name"
    with pytest.raises(build.ConfigError, match="user.name"):
        build.validate_config(cfg)


def test_layer_needs_url_or_path(valid_cfg):
    cfg = copy.deepcopy(valid_cfg)
    cfg["layers"].append({"name": "broken"})
    with pytest.raises(build.ConfigError, match="broken"):
        build.validate_config(cfg)


def test_bad_dns_entry_raises(valid_cfg):
    cfg = copy.deepcopy(valid_cfg)
    cfg["network"]["dns"] = ["not-an-ip"]
    with pytest.raises(build.ConfigError, match="network.dns"):
        build.validate_config(cfg)
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `cd /home/michael/sandbox/rpi4-yocto && python3 -m pytest tests/test_config.py -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'build'` (or `AttributeError` once the file exists).

- [ ] **Step 6: Write `build.py` with loading + validation**

```python
#!/usr/bin/env python3
"""YAML-driven Yocto build orchestrator for the RPi4 image.

Reads project.yml, fetches pinned layers, generates BitBake configuration,
templates the custom layer's network/console files, and runs bitbake.
"""

import ipaddress
import re
import sys
from pathlib import Path

import yaml


class ConfigError(Exception):
    """Raised when project.yml is invalid; message names the offending key."""


USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")

REQUIRED_KEYS = ["name", "machine", "image", "distro", "layers",
                 "user", "network", "console"]


def _require(cfg, dotted_key):
    node = cfg
    for part in dotted_key.split("."):
        if not isinstance(node, dict) or part not in node:
            raise ConfigError(f"missing required key: {dotted_key}")
        node = node[part]
    return node


def _check_ipv4(value, dotted_key):
    try:
        ipaddress.IPv4Address(value)
    except (ipaddress.AddressValueError, ValueError):
        raise ConfigError(f"invalid IPv4 address for {dotted_key}: {value!r}")


def validate_config(cfg):
    if not isinstance(cfg, dict):
        raise ConfigError("top-level YAML must be a mapping")
    for key in REQUIRED_KEYS:
        _require(cfg, key)

    for layer in cfg["layers"]:
        name = layer.get("name", "<unnamed>")
        if "path" in layer:
            continue
        if "url" not in layer or "branch" not in layer:
            raise ConfigError(
                f"layer {name!r} needs either 'path' or 'url' + 'branch'")

    username = _require(cfg, "user.name")
    if not USERNAME_RE.match(str(username)):
        raise ConfigError(f"invalid POSIX username for user.name: {username!r}")
    _require(cfg, "user.password")

    for key in ("network.interface", "network.gateway"):
        _require(cfg, key)
    _check_ipv4(_require(cfg, "network.address"), "network.address")
    _check_ipv4(_require(cfg, "network.gateway"), "network.gateway")

    netmask = _require(cfg, "network.netmask")
    try:
        ipaddress.IPv4Network(f"0.0.0.0/{netmask}")
    except (ipaddress.NetmaskValueError, ValueError):
        raise ConfigError(f"invalid netmask for network.netmask: {netmask!r}")

    dns = _require(cfg, "network.dns")
    if not isinstance(dns, list) or not dns:
        raise ConfigError("network.dns must be a non-empty list")
    for entry in dns:
        _check_ipv4(entry, "network.dns")

    _require(cfg, "console.keymap")
    _require(cfg, "console.font")


def load_config(path):
    with open(path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    validate_config(cfg)
    return cfg


if __name__ == "__main__":
    sys.exit(0)  # replaced by main() in a later task
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: 8 passed. (If `yaml` is missing: `pip install pyyaml pytest` first.)

- [ ] **Step 8: Make `build.py` executable and commit**

```bash
chmod +x build.py
git add .gitignore project.yml build.py tests/conftest.py tests/test_config.py
git commit -m "feat: project.yml schema with loading and validation"
```

---

### Task 2: Password hashing and netmask-to-prefix helpers

**Files:**
- Modify: `build.py` (append functions after `load_config`)
- Test: `tests/test_helpers.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `hash_password(password: str, salt: str | None = None) -> str` — SHA-512 crypt string starting `$6$`, via `openssl passwd -6 -stdin` (random salt when `salt` is None).
- Produces: `netmask_to_prefix(netmask: str) -> int` — e.g. `"255.255.255.0"` → `24`.

- [ ] **Step 1: Write the failing tests**

`tests/test_helpers.py`:

```python
import build


def test_hash_password_is_sha512_crypt():
    h = build.hash_password("michaems", salt="testsalt")
    assert h.startswith("$6$testsalt$")
    # crypt format: $6$<salt>$<86-char hash>
    assert len(h.split("$")[3]) == 86


def test_hash_password_deterministic_with_salt():
    a = build.hash_password("michaems", salt="testsalt")
    b = build.hash_password("michaems", salt="testsalt")
    assert a == b


def test_hash_password_random_salt():
    h = build.hash_password("michaems")
    assert h.startswith("$6$")


def test_netmask_to_prefix():
    assert build.netmask_to_prefix("255.255.255.0") == 24
    assert build.netmask_to_prefix("255.255.0.0") == 16
    assert build.netmask_to_prefix("255.255.255.255") == 32
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_helpers.py -v`
Expected: FAIL with `AttributeError: module 'build' has no attribute 'hash_password'`.

- [ ] **Step 3: Implement the helpers in `build.py`**

Add `import subprocess` to the imports, then append:

```python
def hash_password(password, salt=None):
    """SHA-512 crypt via openssl; avoids the crypt module removed in 3.13.

    The crypt salt alphabet is [./a-zA-Z0-9], so the result can never
    contain '{' and is safe to embed in BitBake conf files.
    """
    cmd = ["openssl", "passwd", "-6", "-stdin"]
    if salt is not None:
        cmd[3:3] = ["-salt", salt]
    result = subprocess.run(cmd, input=password + "\n", capture_output=True,
                            text=True, check=True)
    return result.stdout.strip()


def netmask_to_prefix(netmask):
    return ipaddress.IPv4Network(f"0.0.0.0/{netmask}").prefixlen
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_helpers.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add build.py tests/test_helpers.py
git commit -m "feat: password hashing (openssl SHA-512 crypt) and netmask helpers"
```

---

### Task 3: Config-file generators (local.conf, bblayers.conf, .network, vconsole.conf)

**Files:**
- Modify: `build.py` (append after helpers)
- Test: `tests/test_generate.py`

**Interfaces:**
- Consumes: `hash_password`, `netmask_to_prefix` (Task 2); config dict shape (Task 1).
- Produces: `generate_local_conf(cfg: dict, password_hash: str) -> str`
- Produces: `layer_dirs(cfg: dict, repo_root: Path) -> list[Path]` — absolute BitBake layer directories in project.yml order.
- Produces: `generate_bblayers_conf(cfg: dict, repo_root: Path) -> str`
- Produces: `generate_network_file(cfg: dict) -> str`
- Produces: `generate_vconsole_conf(cfg: dict) -> str`

- [ ] **Step 1: Write the failing tests**

`tests/test_generate.py`:

```python
from pathlib import Path

import build

REPO_ROOT = Path(__file__).resolve().parent.parent
CFG = build.load_config(REPO_ROOT / "project.yml")
HASH = "$6$testsalt$fakehashfortesting"


def test_local_conf_core_settings():
    conf = build.generate_local_conf(CFG, HASH)
    assert 'MACHINE = "raspberrypi4-64"' in conf
    assert 'DISTRO = "poky"' in conf
    assert 'INIT_MANAGER = "systemd"' in conf
    assert 'CONF_VERSION = "2"' in conf


def test_local_conf_user_account():
    conf = build.generate_local_conf(CFG, HASH)
    assert 'INHERIT += "extrausers"' in conf
    assert "groupadd -f sudo;" in conf
    assert f"useradd -m -s /bin/bash -G sudo -p '{HASH}' michaems;" in conf
    assert "usermod -L root;" in conf
    assert "michaems" in conf
    # plaintext password must never appear as a standalone value
    assert "-p 'michaems'" not in conf


def test_local_conf_without_sudo_and_root_lock():
    cfg = {**CFG, "user": {**CFG["user"], "sudo": False},
           "root": {"disable_login": False}}
    conf = build.generate_local_conf(cfg, HASH)
    assert "groupadd" not in conf
    assert "-G sudo" not in conf
    assert "usermod -L root" not in conf


def test_local_conf_image_install():
    conf = build.generate_local_conf(CFG, HASH)
    assert ('IMAGE_INSTALL:append = " sudo sudo-group-conf kbd kbd-keymaps'
            ' terminus-font-consolefonts"') in conf


def test_local_conf_extra_lines():
    cfg = {**CFG, "local_conf_extra": ['ENABLE_UART = "1"']}
    conf = build.generate_local_conf(cfg, HASH)
    assert 'ENABLE_UART = "1"' in conf


def test_layer_dirs_order_and_paths():
    dirs = build.layer_dirs(CFG, REPO_ROOT)
    rel = [str(d.relative_to(REPO_ROOT)) for d in dirs]
    assert rel == [
        "layers/poky/meta",
        "layers/poky/meta-poky",
        "layers/poky/meta-yocto-bsp",
        "layers/meta-raspberrypi",
        "layers/meta-openembedded/meta-oe",
        "meta-rpi4-custom",
    ]


def test_bblayers_conf():
    conf = build.generate_bblayers_conf(CFG, REPO_ROOT)
    assert 'POKY_BBLAYERS_CONF_VERSION = "2"' in conf
    assert 'BBPATH = "${TOPDIR}"' in conf
    assert str(REPO_ROOT / "layers/poky/meta") in conf
    assert str(REPO_ROOT / "meta-rpi4-custom") in conf


def test_network_file():
    assert build.generate_network_file(CFG) == """\
[Match]
Name=eth0

[Network]
Address=192.168.100.180/24
Gateway=192.168.100.1
DNS=192.168.100.1
"""


def test_network_file_multiple_dns():
    cfg = {**CFG, "network": {**CFG["network"],
                              "dns": ["192.168.100.1", "8.8.8.8"]}}
    out = build.generate_network_file(cfg)
    assert "DNS=192.168.100.1\n" in out
    assert "DNS=8.8.8.8\n" in out


def test_vconsole_conf():
    assert build.generate_vconsole_conf(CFG) == "KEYMAP=fi\nFONT=ter-v16n\n"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_generate.py -v`
Expected: FAIL with `AttributeError: module 'build' has no attribute 'generate_local_conf'`.

- [ ] **Step 3: Implement the generators in `build.py`**

Append (note: `groupadd -f` not `-r`, so the build survives if a base package already provides the group; templates avoid `str.format` where BitBake's `${TOPDIR}` would collide with Python braces):

```python
GENERATED_HEADER = "# Generated by build.py from project.yml -- do not edit by hand.\n"

IMAGE_EXTRA_PACKAGES = "sudo sudo-group-conf kbd kbd-keymaps terminus-font-consolefonts"


def _extra_users_params(cfg, password_hash):
    user = cfg["user"]
    parts = []
    if user.get("sudo", False):
        parts.append("groupadd -f sudo;")
        group_opt = " -G sudo"
    else:
        group_opt = ""
    parts.append(
        f"useradd -m -s /bin/bash{group_opt} -p '{password_hash}' {user['name']};")
    if cfg.get("root", {}).get("disable_login", True):
        parts.append("usermod -L root;")
    return " ".join(parts)


def generate_local_conf(cfg, password_hash):
    lines = [
        GENERATED_HEADER,
        f'MACHINE = "{cfg["machine"]}"',
        f'DISTRO = "{cfg["distro"]}"',
        'INIT_MANAGER = "systemd"',
        '',
        'IMAGE_FSTYPES = "wic.bz2 wic.bmap"',
        '',
        'INHERIT += "extrausers"',
        f'EXTRA_USERS_PARAMS = "{_extra_users_params(cfg, password_hash)}"',
        '',
        f'IMAGE_INSTALL:append = " {IMAGE_EXTRA_PACKAGES}"',
        '',
        'CONF_VERSION = "2"',
    ]
    lines += cfg.get("local_conf_extra") or []
    return "\n".join(lines) + "\n"


def layer_dirs(cfg, repo_root):
    dirs = []
    for layer in cfg["layers"]:
        if "path" in layer:
            dirs.append(repo_root / layer["path"])
        else:
            base = repo_root / "layers" / layer["name"]
            for sub in layer.get("layers") or [None]:
                dirs.append(base / sub if sub else base)
    return dirs


def generate_bblayers_conf(cfg, repo_root):
    entries = "".join(f"  {d} \\\n" for d in layer_dirs(cfg, repo_root))
    return (
        GENERATED_HEADER
        + 'POKY_BBLAYERS_CONF_VERSION = "2"\n'
        + 'BBPATH = "${TOPDIR}"\n'
        + 'BBFILES ?= ""\n'
        + 'BBLAYERS ?= " \\\n'
        + entries
        + '"\n'
    )


def generate_network_file(cfg):
    net = cfg["network"]
    prefix = netmask_to_prefix(net["netmask"])
    dns_lines = "".join(f"DNS={entry}\n" for entry in net["dns"])
    return (
        f"[Match]\nName={net['interface']}\n\n"
        f"[Network]\nAddress={net['address']}/{prefix}\n"
        f"Gateway={net['gateway']}\n{dns_lines}"
    )


def generate_vconsole_conf(cfg):
    console = cfg["console"]
    return f"KEYMAP={console['keymap']}\nFONT={console['font']}\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_generate.py -v`
Expected: 10 passed.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest tests/ -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add build.py tests/test_generate.py
git commit -m "feat: generate local.conf, bblayers.conf, .network and vconsole.conf"
```

---

### Task 4: Custom layer meta-rpi4-custom

**Files:**
- Create: `meta-rpi4-custom/conf/layer.conf`
- Create: `meta-rpi4-custom/recipes-core/sudo-group-conf/sudo-group-conf_1.0.bb`
- Create: `meta-rpi4-custom/recipes-core/sudo-group-conf/files/sudo-group`
- Create: `meta-rpi4-custom/recipes-core/systemd-conf/systemd-conf_%.bbappend`
- Create: `meta-rpi4-custom/recipes-core/systemd-conf/files/10-static.network`
- Create: `meta-rpi4-custom/recipes-core/systemd-conf/files/vconsole.conf`

**Interfaces:**
- Consumes: nothing from Python code. The two `files/` payloads are the committed defaults; Task 5's `write_outputs` regenerates them from `project.yml` (content must match `generate_network_file`/`generate_vconsole_conf` output for the default config).
- Produces: package `sudo-group-conf` and the bbappend, referenced by `IMAGE_INSTALL:append` from Task 3's `local.conf`.

No pytest here (declarative BitBake metadata); verification is content inspection now and the BitBake parse in Task 7.

- [ ] **Step 1: Create `meta-rpi4-custom/conf/layer.conf`**

```
BBPATH .= ":${LAYERDIR}"

BBFILES += "${LAYERDIR}/recipes-*/*/*.bb \
            ${LAYERDIR}/recipes-*/*/*.bbappend"

BBFILE_COLLECTIONS += "rpi4-custom"
BBFILE_PATTERN_rpi4-custom = "^${LAYERDIR}/"
BBFILE_PRIORITY_rpi4-custom = "10"

LAYERDEPENDS_rpi4-custom = "core"
LAYERSERIES_COMPAT_rpi4-custom = "scarthgap"
```

- [ ] **Step 2: Create the sudoers drop-in payload**

`meta-rpi4-custom/recipes-core/sudo-group-conf/files/sudo-group`:

```
%sudo ALL=(ALL:ALL) ALL
```

- [ ] **Step 3: Create `meta-rpi4-custom/recipes-core/sudo-group-conf/sudo-group-conf_1.0.bb`**

```
SUMMARY = "Grant sudo rights to the sudo group"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://sudo-group"

S = "${WORKDIR}"

do_install() {
    install -d ${D}${sysconfdir}/sudoers.d
    install -m 0440 ${WORKDIR}/sudo-group ${D}${sysconfdir}/sudoers.d/sudo-group
}

RDEPENDS:${PN} = "sudo"
```

- [ ] **Step 4: Create the default templated payloads**

`meta-rpi4-custom/recipes-core/systemd-conf/files/10-static.network` (must byte-match `generate_network_file` output for the default `project.yml`):

```
[Match]
Name=eth0

[Network]
Address=192.168.100.180/24
Gateway=192.168.100.1
DNS=192.168.100.1
```

`meta-rpi4-custom/recipes-core/systemd-conf/files/vconsole.conf`:

```
KEYMAP=fi
FONT=ter-v16n
```

- [ ] **Step 5: Create `meta-rpi4-custom/recipes-core/systemd-conf/systemd-conf_%.bbappend`**

The `PACKAGECONFIG:remove` drops OE-core's default `80-wired.network` DHCP config so it cannot race our static config; the `10-` prefix additionally sorts first:

```
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += "file://10-static.network \
            file://vconsole.conf"

PACKAGECONFIG:remove = "dhcp-ethernet"

do_install:append() {
    install -d ${D}${systemd_unitdir}/network
    install -m 0644 ${WORKDIR}/10-static.network ${D}${systemd_unitdir}/network/10-static.network
    install -d ${D}${sysconfdir}
    install -m 0644 ${WORKDIR}/vconsole.conf ${D}${sysconfdir}/vconsole.conf
}

FILES:${PN} += "${systemd_unitdir}/network ${sysconfdir}/vconsole.conf"
```

- [ ] **Step 6: Verify layer file tree**

Run: `find meta-rpi4-custom -type f | sort`
Expected output:

```
meta-rpi4-custom/conf/layer.conf
meta-rpi4-custom/recipes-core/sudo-group-conf/files/sudo-group
meta-rpi4-custom/recipes-core/sudo-group-conf/sudo-group-conf_1.0.bb
meta-rpi4-custom/recipes-core/systemd-conf/files/10-static.network
meta-rpi4-custom/recipes-core/systemd-conf/files/vconsole.conf
meta-rpi4-custom/recipes-core/systemd-conf/systemd-conf_%.bbappend
```

- [ ] **Step 7: Commit**

```bash
git add meta-rpi4-custom/
git commit -m "feat: meta-rpi4-custom layer (static IP, vconsole, sudo group)"
```

---

### Task 5: Layer fetching and output writing

**Files:**
- Modify: `build.py` (append after generators)
- Test: `tests/test_fetch.py`

**Interfaces:**
- Consumes: generators from Task 3, `hash_password` from Task 2, config shape from Task 1.
- Produces: `fetch_layers(cfg: dict, layers_dir: Path) -> None` — clone or update each remote layer; raises `FetchError` on dirty checkouts.
- Produces: `FetchError` exception class.
- Produces: `write_outputs(cfg: dict, repo_root: Path) -> None` — writes `build/conf/local.conf`, `build/conf/bblayers.conf`, and the two templated files under `meta-rpi4-custom/recipes-core/systemd-conf/files/`.

- [ ] **Step 1: Write the failing tests**

`tests/test_fetch.py` (uses throwaway local git repos as origins — no network):

```python
import subprocess
from pathlib import Path

import pytest

import build

REPO_ROOT = Path(__file__).resolve().parent.parent


def make_origin(path, branch="scarthgap"):
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", branch, str(path)], check=True,
                   capture_output=True)
    (path / "README").write_text("layer\n")
    subprocess.run(["git", "-C", str(path), "add", "README"], check=True)
    subprocess.run(["git", "-C", str(path), "-c", "user.email=t@t",
                    "-c", "user.name=t", "commit", "-m", "init"],
                   check=True, capture_output=True)
    return path


def layer_cfg(origin, name="testlayer"):
    return {"layers": [{"name": name, "url": str(origin),
                        "branch": "scarthgap"}]}


def test_fetch_clones_missing_layer(tmp_path):
    origin = make_origin(tmp_path / "origin")
    layers_dir = tmp_path / "layers"
    build.fetch_layers(layer_cfg(origin), layers_dir)
    assert (layers_dir / "testlayer" / "README").exists()


def test_fetch_updates_existing_clone(tmp_path):
    origin = make_origin(tmp_path / "origin")
    layers_dir = tmp_path / "layers"
    build.fetch_layers(layer_cfg(origin), layers_dir)
    (origin / "NEW").write_text("x\n")
    subprocess.run(["git", "-C", str(origin), "add", "NEW"], check=True)
    subprocess.run(["git", "-C", str(origin), "-c", "user.email=t@t",
                    "-c", "user.name=t", "commit", "-m", "more"],
                   check=True, capture_output=True)
    build.fetch_layers(layer_cfg(origin), layers_dir)
    assert (layers_dir / "testlayer" / "NEW").exists()


def test_fetch_refuses_dirty_clone(tmp_path):
    origin = make_origin(tmp_path / "origin")
    layers_dir = tmp_path / "layers"
    cfg = layer_cfg(origin)
    build.fetch_layers(cfg, layers_dir)
    (layers_dir / "testlayer" / "README").write_text("local change\n")
    with pytest.raises(build.FetchError, match="testlayer"):
        build.fetch_layers(cfg, layers_dir)


def test_fetch_checks_out_pinned_rev(tmp_path):
    origin = make_origin(tmp_path / "origin")
    first = subprocess.run(["git", "-C", str(origin), "rev-parse", "HEAD"],
                           check=True, capture_output=True,
                           text=True).stdout.strip()
    (origin / "NEW").write_text("x\n")
    subprocess.run(["git", "-C", str(origin), "add", "NEW"], check=True)
    subprocess.run(["git", "-C", str(origin), "-c", "user.email=t@t",
                    "-c", "user.name=t", "commit", "-m", "more"],
                   check=True, capture_output=True)
    cfg = layer_cfg(origin)
    cfg["layers"][0]["rev"] = first
    layers_dir = tmp_path / "layers"
    build.fetch_layers(cfg, layers_dir)
    assert not (layers_dir / "testlayer" / "NEW").exists()


def test_fetch_skips_local_path_layers(tmp_path):
    cfg = {"layers": [{"name": "meta-rpi4-custom",
                       "path": "meta-rpi4-custom"}]}
    build.fetch_layers(cfg, tmp_path / "layers")
    assert not (tmp_path / "layers").exists() or \
        not any((tmp_path / "layers").iterdir())


def test_write_outputs(tmp_path, monkeypatch):
    cfg = build.load_config(REPO_ROOT / "project.yml")
    monkeypatch.setattr(build, "hash_password",
                        lambda pw, salt=None: "$6$testsalt$fakehash")
    src = tmp_path / "repo"
    (src / "meta-rpi4-custom/recipes-core/systemd-conf/files").mkdir(
        parents=True)
    build.write_outputs(cfg, src)
    local_conf = (src / "build/conf/local.conf").read_text()
    assert "$6$testsalt$fakehash" in local_conf
    assert "michaems" in local_conf
    bblayers = (src / "build/conf/bblayers.conf").read_text()
    assert str(src / "meta-rpi4-custom") in bblayers
    net = (src / "meta-rpi4-custom/recipes-core/systemd-conf/files/"
                 "10-static.network").read_text()
    assert "Address=192.168.100.180/24" in net
    vconsole = (src / "meta-rpi4-custom/recipes-core/systemd-conf/files/"
                      "vconsole.conf").read_text()
    assert vconsole == "KEYMAP=fi\nFONT=ter-v16n\n"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_fetch.py -v`
Expected: FAIL with `AttributeError: module 'build' has no attribute 'fetch_layers'`.

- [ ] **Step 3: Implement fetching and output writing in `build.py`**

Append:

```python
class FetchError(Exception):
    """Raised when a layer checkout cannot be safely updated."""


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          check=True, capture_output=True, text=True)


def fetch_layers(cfg, layers_dir):
    for layer in cfg["layers"]:
        if "path" in layer:
            continue
        dest = Path(layers_dir) / layer["name"]
        branch = layer["branch"]
        if not dest.exists():
            print(f"Cloning {layer['name']} ({branch})...")
            subprocess.run(["git", "clone", "--branch", branch,
                            layer["url"], str(dest)], check=True)
        else:
            status = _git(dest, "status", "--porcelain").stdout
            if status.strip():
                raise FetchError(
                    f"layer checkout {layer['name']} at {dest} has local "
                    f"changes; commit/stash them or remove the directory")
            print(f"Updating {layer['name']} ({branch})...")
            _git(dest, "fetch", "origin")
        if "rev" in layer:
            _git(dest, "checkout", "--detach", layer["rev"])
        else:
            _git(dest, "checkout", "-B", branch, f"origin/{branch}")


def write_outputs(cfg, repo_root):
    repo_root = Path(repo_root)
    conf_dir = repo_root / "build" / "conf"
    conf_dir.mkdir(parents=True, exist_ok=True)

    password_hash = hash_password(cfg["user"]["password"])
    (conf_dir / "local.conf").write_text(
        generate_local_conf(cfg, password_hash))
    (conf_dir / "bblayers.conf").write_text(
        generate_bblayers_conf(cfg, repo_root))

    files_dir = (repo_root / "meta-rpi4-custom" / "recipes-core"
                 / "systemd-conf" / "files")
    (files_dir / "10-static.network").write_text(generate_network_file(cfg))
    (files_dir / "vconsole.conf").write_text(generate_vconsole_conf(cfg))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_fetch.py -v`
Expected: 6 passed.

- [ ] **Step 5: Confirm committed defaults match generated output**

Run: `python3 -c "
import build
from pathlib import Path
cfg = build.load_config(Path('project.yml'))
assert Path('meta-rpi4-custom/recipes-core/systemd-conf/files/10-static.network').read_text() == build.generate_network_file(cfg)
assert Path('meta-rpi4-custom/recipes-core/systemd-conf/files/vconsole.conf').read_text() == build.generate_vconsole_conf(cfg)
print('defaults in sync')
"`
Expected: `defaults in sync`

- [ ] **Step 6: Commit**

```bash
git add build.py tests/test_fetch.py
git commit -m "feat: layer fetching with dirty-checkout guard and output writing"
```

---

### Task 6: Orchestration — prereq check, bitbake invocation, main()

**Files:**
- Modify: `build.py` (append; replace the `if __name__` block)
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `load_config`, `fetch_layers`, `write_outputs` (earlier tasks).
- Produces: `check_host_prereqs() -> None` — raises `SystemExit` naming any missing tool from `REQUIRED_TOOLS = ["git", "tar", "bash", "openssl", "gcc"]`.
- Produces: `run_bitbake(cfg: dict, repo_root: Path) -> int` — sources `layers/poky/oe-init-build-env build` and runs `bitbake <image>`; returns the exit code and prints the deploy dir on success.
- Produces: `main(argv: list[str] | None = None) -> int` — CLI: `--config` (default `project.yml`), `--no-build`.

- [ ] **Step 1: Write the failing tests**

`tests/test_main.py`:

```python
from pathlib import Path

import pytest

import build


def test_check_host_prereqs_passes_on_dev_host():
    build.check_host_prereqs()  # git/tar/bash/openssl/gcc exist here


def test_check_host_prereqs_fails_on_missing_tool(monkeypatch):
    monkeypatch.setattr(build.shutil, "which",
                        lambda tool: None if tool == "gcc" else "/usr/bin/x")
    with pytest.raises(SystemExit, match="gcc"):
        build.check_host_prereqs()


def test_main_no_build_runs_setup_only(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(build, "check_host_prereqs",
                        lambda: calls.append("prereqs"))
    monkeypatch.setattr(build, "fetch_layers",
                        lambda cfg, d: calls.append("fetch"))
    monkeypatch.setattr(build, "write_outputs",
                        lambda cfg, r: calls.append("write"))
    monkeypatch.setattr(build, "run_bitbake",
                        lambda cfg, r: calls.append("bitbake") or 0)
    rc = build.main(["--no-build"])
    assert rc == 0
    assert calls == ["prereqs", "fetch", "write"]  # no bitbake


def test_main_full_runs_bitbake(monkeypatch):
    monkeypatch.setattr(build, "check_host_prereqs", lambda: None)
    monkeypatch.setattr(build, "fetch_layers", lambda cfg, d: None)
    monkeypatch.setattr(build, "write_outputs", lambda cfg, r: None)
    monkeypatch.setattr(build, "run_bitbake", lambda cfg, r: 7)
    assert build.main([]) == 7


def test_main_invalid_config_exits_with_error(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("name: x\n")
    with pytest.raises(SystemExit, match="missing required key"):
        build.main(["--config", str(bad)])


def test_run_bitbake_command_shape(monkeypatch):
    cfg = {"image": "core-image-full-cmdline",
           "machine": "raspberrypi4-64"}
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd

        class R:
            returncode = 0
        return R()

    monkeypatch.setattr(build.subprocess, "run", fake_run)
    rc = build.run_bitbake(cfg, Path("/repo"))
    assert rc == 0
    assert captured["cmd"][0] == "bash"
    assert "oe-init-build-env" in captured["cmd"][2]
    assert "bitbake core-image-full-cmdline" in captured["cmd"][2]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_main.py -v`
Expected: FAIL with `AttributeError: module 'build' has no attribute 'check_host_prereqs'`.

- [ ] **Step 3: Implement orchestration in `build.py`**

Add `import argparse`, `import shlex`, `import shutil` to the imports. Append, and replace the placeholder `if __name__ == "__main__":` block at the bottom of the file:

```python
REQUIRED_TOOLS = ["git", "tar", "bash", "openssl", "gcc"]


def check_host_prereqs():
    missing = [t for t in REQUIRED_TOOLS if shutil.which(t) is None]
    if missing:
        raise SystemExit(
            f"missing host tools: {', '.join(missing)} — install them and "
            f"see the Yocto quick start for full host requirements")


def run_bitbake(cfg, repo_root):
    repo_root = Path(repo_root)
    env_script = repo_root / "layers" / "poky" / "oe-init-build-env"
    build_dir = repo_root / "build"
    shell_cmd = (f"source {shlex.quote(str(env_script))} "
                 f"{shlex.quote(str(build_dir))} && "
                 f"bitbake {shlex.quote(cfg['image'])}")
    proc = subprocess.run(["bash", "-c", shell_cmd], cwd=str(repo_root))
    if proc.returncode == 0:
        deploy = build_dir / "tmp" / "deploy" / "images" / cfg["machine"]
        print(f"\nBuild OK. Flashable image in: {deploy}")
    return proc.returncode


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build the RPi4 Yocto image described by project.yml")
    parser.add_argument("--config", default="project.yml",
                        help="path to the project YAML (default: project.yml)")
    parser.add_argument("--no-build", action="store_true",
                        help="fetch layers and generate config, skip bitbake")
    args = parser.parse_args(argv)

    try:
        cfg = load_config(Path(args.config))
    except (ConfigError, OSError, yaml.YAMLError) as exc:
        raise SystemExit(f"config error: {exc}")

    check_host_prereqs()
    repo_root = Path(__file__).resolve().parent
    try:
        fetch_layers(cfg, repo_root / "layers")
    except (FetchError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"layer fetch failed: {exc}")
    write_outputs(cfg, repo_root)

    if args.no_build:
        print("Setup complete (--no-build): layers fetched, config written.")
        return 0
    return run_bitbake(cfg, repo_root)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_main.py -v`
Expected: 6 passed.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest tests/ -v`
Expected: all tests pass (config 8, helpers 4, generate 10, fetch 6, main 6 = 34).

- [ ] **Step 6: Commit**

```bash
git add build.py tests/test_main.py
git commit -m "feat: orchestration - prereq check, bitbake invocation, CLI"
```

---

### Task 7: README, setup verification, BitBake parse check

**Files:**
- Modify: `README.md`
- (verification only — no other file changes expected; fix-forward if the parse check surfaces issues in `meta-rpi4-custom` or generated conf)

**Interfaces:**
- Consumes: the complete `./build.py` CLI from Task 6.
- Produces: user-facing documentation; verified layer/conf setup.

- [ ] **Step 1: Rewrite `README.md`**

```markdown
# rpi4-yocto

Builds a bootable Yocto (Scarthgap LTS) image for the Raspberry Pi 4 Model B
(64-bit) from a single YAML file, `project.yml`.

The image has:

- systemd init
- user `michaems` / password `michaems`, with sudo; root login disabled
- static IP **192.168.100.180/24** on `eth0`, gateway/DNS 192.168.100.1
- SSH server (`ssh michaems@192.168.100.180`)
- Finnish console keymap (`fi`) and Terminus console font (`ter-v16n`)

## Requirements

- A Linux host matching the [Yocto system requirements]
  (https://docs.yoctoproject.org/scarthgap/ref-manual/system-requirements.html)
  (Ubuntu/Debian: `sudo apt install gawk wget git diffstat unzip texinfo
  gcc build-essential chrpath socat cpio python3 python3-pip python3-pexpect
  xz-utils debianutils iputils-ping python3-git python3-jinja2 libsdl1.2-dev
  python3-subunit mesa-common-dev zstd liblz4-tool file locales`)
- `python3` with PyYAML (`pip install pyyaml`), plus `pytest` for the tests
- ~50 GB free disk, several hours for the first build

## Usage

```bash
./build.py               # fetch layers, generate config, build the image
./build.py --no-build    # stop after layer fetch + config generation
python3 -m pytest tests/ # unit tests (fast, no Yocto needed)
```

Everything (machine, image, user, network, console) is configured in
`project.yml`; edit it and re-run `./build.py`.

## Flashing

The build drops the image in
`build/tmp/deploy/images/raspberrypi4-64/`:

```bash
# with bmaptool (faster):
sudo bmaptool copy \
  build/tmp/deploy/images/raspberrypi4-64/core-image-full-cmdline-raspberrypi4-64.rootfs.wic.bz2 \
  /dev/sdX
# or with dd:
bzcat build/tmp/deploy/images/raspberrypi4-64/core-image-full-cmdline-raspberrypi4-64.rootfs.wic.bz2 \
  | sudo dd of=/dev/sdX bs=4M status=progress conv=fsync
```

Replace `/dev/sdX` with your SD card device (check with `lsblk`).

## On-target checklist

1. Board boots to a login prompt on HDMI, rendered in Terminus font.
2. Finnish layout: ö, ä, å type correctly on the console.
3. `ip addr show eth0` shows `192.168.100.180/24`.
4. From another machine: `ssh michaems@192.168.100.180` (password
   `michaems`) works.
5. `sudo whoami` prints `root`.
6. `su root` and SSH as root are refused.

## Layout

| Path | Purpose |
|---|---|
| `project.yml` | single source of truth for the whole image |
| `build.py` | orchestrator: validate → fetch layers → generate conf → bitbake |
| `meta-rpi4-custom/` | custom layer: static IP, vconsole, sudoers drop-in |
| `layers/` | cloned upstream layers (git-ignored) |
| `build/` | BitBake build dir (git-ignored) |
```

- [ ] **Step 2: Commit the README**

```bash
git add README.md
git commit -m "docs: usage, flashing and on-target checklist"
```

- [ ] **Step 3: Run setup end-to-end (no build)**

Run: `./build.py --no-build`
Expected: clones poky, meta-raspberrypi, meta-openembedded (few GB of git traffic, several minutes), then `Setup complete (--no-build): layers fetched, config written.` and exit code 0.

- [ ] **Step 4: Verify generated artifacts**

Run: `ls build/conf/ && grep MACHINE build/conf/local.conf && grep -c '$6$' build/conf/local.conf`
Expected: `bblayers.conf local.conf`, `MACHINE = "raspberrypi4-64"`, `1` (the hash, no plaintext).

- [ ] **Step 5: BitBake parse check (validates layer + bbappend without building)**

Run: `bash -c 'source layers/poky/oe-init-build-env build && bitbake -p && bitbake-layers show-layers'`
Expected: parse completes with no errors; layer list includes `meta-rpi4-custom` (priority 10), `meta-raspberrypi`, `meta-oe`. If the host is missing Yocto prerequisites, install the apt list from the README and rerun. If `systemd-conf` has no `dhcp-ethernet` PACKAGECONFIG in this release, `PACKAGECONFIG:remove` is a harmless no-op — the `10-` filename ordering still wins; verify instead with `bitbake -e systemd-conf | grep '^SRC_URI='` showing `10-static.network`.

- [ ] **Step 6: Commit any parse fixes**

```bash
git status  # only commit if step 5 required fixes
git add -u && git commit -m "fix: bitbake parse fixes for custom layer"  # if needed
```

- [ ] **Step 7 (manual, optional — hours): Full build**

Run: `./build.py`
Expected: BitBake builds `core-image-full-cmdline`; final output
`build/tmp/deploy/images/raspberrypi4-64/core-image-full-cmdline-raspberrypi4-64.rootfs.wic.bz2` (+ `.wic.bmap`). Then flash and walk the README on-target checklist.
