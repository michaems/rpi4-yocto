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
