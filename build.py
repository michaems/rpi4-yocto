#!/usr/bin/env python3
"""YAML-driven Yocto build orchestrator for the RPi4 image.

Reads project.yml, fetches pinned layers, generates BitBake configuration,
templates the custom layer's network/console files, and runs bitbake.
"""

import ipaddress
import re
import subprocess
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


if __name__ == "__main__":
    sys.exit(0)  # replaced by main() in a later task
