"""Tests for selects.proxies."""

from pathlib import Path

from selects.proxies import build_proxy_command, proxy_path_for


def test_proxy_path_for_adds_suffix():
    assert proxy_path_for(Path("/footage/C0001.MP4"), Path("proxies")) == Path(
        "proxies/C0001_proxy.mp4"
    )


def test_proxy_command_applies_lut_for_log_clips():
    command = build_proxy_command(Path("in.MP4"), Path("out.mp4"), Path("/luts/sony.cube"))
    filters = command[command.index("-vf") + 1]

    assert "scale=-2:720" in filters
    assert "lut3d=file='/luts/sony.cube'" in filters
    assert command[-1] == "out.mp4"


def test_proxy_command_without_lut_only_scales():
    command = build_proxy_command(Path("in.MP4"), Path("out.mp4"), None)
    filters = command[command.index("-vf") + 1]

    assert "scale=-2:720" in filters
    assert "lut3d" not in filters
