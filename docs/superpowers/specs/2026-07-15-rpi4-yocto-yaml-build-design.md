# RPi4 Yocto YAML-Driven Build — Design

**Date:** 2026-07-15
**Status:** Approved

## Goal

A repository that builds a bootable Raspberry Pi 4 (64-bit) Yocto image from a
single YAML configuration file. The image must have:

- User `michaems` with password `michaems`, sudo rights
- Root login disabled
- Static IP `192.168.100.180/24` on `eth0`, gateway and DNS `192.168.100.1`
- SSH access (`ssh michaems@192.168.100.180`)
- Finnish keyboard layout and a Courier-like console font (Terminus) on the
  HDMI console

## Decisions

| Decision | Choice |
|---|---|
| Build tool | Custom Python orchestrator + YAML config (no kas) |
| Yocto release | Scarthgap 5.0 LTS (supported until April 2028) |
| Machine | `raspberrypi4-64` |
| Image | `core-image-full-cmdline` (includes OpenSSH and sudo) |
| Init/networking | systemd (`INIT_MANAGER = "systemd"`) + systemd-networkd/resolved |
| Console | Finnish keymap (`KEYMAP=fi`) + Terminus font (`ter-v16n`) via `/etc/vconsole.conf` |
| Layers | poky, meta-raspberrypi, meta-openembedded/meta-oe (all `scarthgap` branch), meta-rpi4-custom (local) |

The original ask was Courier New as the console font. The Linux virtual
console renders only bitmap PSF fonts, and Courier New is a proprietary
Microsoft TrueType font that cannot be redistributed in a Yocto build, so the
agreed substitute is Terminus (`ter-v16n`), the closest Courier-like console
font. Over SSH the font is chosen by the client terminal, where Courier New
can be set directly. meta-oe is required for the `terminus-font` recipe.

## Repository layout

```
rpi4-yocto/
├── project.yml              # single source of truth
├── build.py                 # orchestrator: parse YAML → fetch layers → generate conf → bitbake
├── meta-rpi4-custom/        # small custom layer, committed to git
│   ├── conf/layer.conf
│   └── recipes-core/
│       ├── systemd-conf/    # bbappend: templated .network file (static IP + DNS)
│       │                    #           + vconsole.conf (fi keymap, Terminus font)
│       └── sudo-group-conf/ # /etc/sudoers.d/sudo-group enabling %sudo
├── layers/                  # git-ignored; poky + meta-raspberrypi cloned here
├── build/                   # git-ignored; generated conf/ + BitBake output
├── tests/                   # pytest suite for config generation
├── docs/superpowers/specs/
├── README.md
└── .gitignore
```

## Data flow

1. User edits `project.yml`.
2. `./build.py` (optionally `--no-build` to stop after setup):
   - validates the YAML,
   - clones or updates poky and meta-raspberrypi into `layers/` at their
     pinned branch (or `rev` if given),
   - writes `build/conf/bblayers.conf` and `build/conf/local.conf`
     (including `INIT_MANAGER = "systemd"`),
   - hashes the password (SHA-512 crypt) and injects it via `extrausers`,
   - templates the static-IP systemd `.network` file into `meta-rpi4-custom`
     from the YAML values,
   - sources the Yocto environment and runs `bitbake <image>`.
3. Output: `build/tmp/deploy/images/raspberrypi4-64/core-image-full-cmdline-raspberrypi4-64.rootfs.wic.bz2`
   (plus `.wic.bmap`), flashable with `bmaptool` or `dd`.

## project.yml schema

```yaml
name: rpi4-yocto
machine: raspberrypi4-64
image: core-image-full-cmdline
distro: poky

layers:
  - name: poky
    url: https://git.yoctoproject.org/poky
    branch: scarthgap
    # optional: rev: <sha> for exact pinning
    # sub-layers used: meta, meta-poky, meta-yocto-bsp
  - name: meta-raspberrypi
    url: https://git.yoctoproject.org/meta-raspberrypi
    branch: scarthgap
  - name: meta-openembedded
    url: https://git.openembedded.org/meta-openembedded
    branch: scarthgap
    layers: [meta-oe]             # sub-layers to add to bblayers.conf
  - name: meta-rpi4-custom
    path: meta-rpi4-custom        # local layer, no clone

user:
  name: michaems
  password: michaems              # plaintext here; hashed at build time
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
  keymap: fi                      # Finnish keyboard layout
  font: ter-v16n                  # Terminus 16px, Courier-like

local_conf_extra: []              # optional raw local.conf lines
```

Storing the password in plaintext in `project.yml` is an accepted trade-off
for this sandbox project; only its SHA-512 hash reaches the image.

## System configuration details

### User account

`build.py` injects into `local.conf`:

```
INHERIT += "extrausers"
EXTRA_USERS_PARAMS = "groupadd -r sudo; useradd -m -s /bin/bash -G sudo -p '<sha512-hash>' michaems; usermod -L root;"
```

- Hash computed by `build.py` from the YAML password.
- `usermod -L root` locks root; `debug-tweaks` is not enabled, so there is no
  empty-root-password fallback. SSH root login is refused as a consequence.

### Sudo

`core-image-full-cmdline` ships the `sudo` package, but the `sudo` group has
no rights by default. The `sudo-group-conf` recipe installs
`/etc/sudoers.d/sudo-group` containing `%sudo ALL=(ALL:ALL) ALL` and is added
via `IMAGE_INSTALL:append` in the generated `local.conf`.

### Init system

The generated `local.conf` sets `INIT_MANAGER = "systemd"`, which switches the
distro features and virtual runtime providers to systemd. Networking is
handled by systemd-networkd with name resolution via systemd-resolved (both
enabled by default in the Yocto systemd package).

### Static IP and DNS

OE-core's `systemd-conf` recipe ships the default network config. The custom
layer carries a `systemd-conf` bbappend whose `.network` file `build.py`
templates from the YAML, replacing the default DHCP config for the chosen
interface:

```
[Match]
Name=eth0

[Network]
Address=192.168.100.180/24
Gateway=192.168.100.1
DNS=192.168.100.1
```

DNS needs no separate recipe: systemd-resolved picks up the `DNS=` entry and
manages `/etc/resolv.conf`. (The YAML `netmask` is converted to prefix length
for the `Address=` line.)

### Console keymap and font

The same `systemd-conf` bbappend installs `/etc/vconsole.conf`, templated from
the YAML `console` section:

```
KEYMAP=fi
FONT=ter-v16n
```

systemd-vconsole-setup applies both at boot. The generated `local.conf` adds
the required packages via `IMAGE_INSTALL:append`: `kbd`, `kbd-keymaps`
(Finnish keymap data) and `terminus-font-consolefonts` (from meta-oe).
This affects the HDMI console only; SSH sessions use the client terminal's
own font, where Courier New can be selected.

## Error handling (build.py)

- Up-front schema validation: required keys, valid IPv4 for
  address/netmask/gateway/dns (`ipaddress` stdlib), POSIX-valid username,
  each layer entry has either `url`+`branch` or `path`. Fail fast, naming the
  offending key.
- Host prerequisite check (git, python3, tar — short sanity list; Yocto's own
  host checks cover the rest).
- Layer fetch: existing clones are `git fetch`ed and checked out to the pinned
  branch/rev; dirty checkouts abort with a clear message instead of discarding
  changes.
- BitBake failures propagate as-is; `build.py` exits with BitBake's exit code
  and prints the deploy directory on success.

## Testing

- **Unit (pytest, fast, no Yocto):** sample YAML produces expected
  `local.conf`, `bblayers.conf`, systemd `.network` file (including
  netmask→prefix conversion), and `vconsole.conf`; password hash verifies
  against `michaems`; invalid input (bad IP, missing keys) is rejected.
- **Build verification (manual):** `./build.py` completes and produces the
  `.wic.bz2` image.
- **On-target checklist (documented in README):** board boots; `ip addr`
  shows 192.168.100.180; `ssh michaems@192.168.100.180` works with password
  `michaems`; `sudo whoami` prints `root`; root login (`su root`, SSH as
  root) fails; HDMI console renders the Terminus font and Finnish keys
  (ö, ä, å) type correctly.
- No CI: a full Yocto build needs ~50 GB disk and hours of CPU; out of scope
  for this sandbox repository.

## Out of scope

- WiFi configuration
- Literal Courier New rendering on target (needs a GUI stack + proprietary
  font; Terminus substitutes on console, Courier New is set client-side for
  SSH)
- kas or CI pipelines
- Additional image features beyond `core-image-full-cmdline`
