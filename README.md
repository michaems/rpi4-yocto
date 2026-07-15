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
