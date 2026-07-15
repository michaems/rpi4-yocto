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
