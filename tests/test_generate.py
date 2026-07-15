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
