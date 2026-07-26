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
