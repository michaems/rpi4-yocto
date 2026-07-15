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
