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
