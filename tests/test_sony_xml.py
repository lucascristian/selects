"""Tests for selects.sony_xml."""

import pytest

from selects.sony_xml import find_sidecar_xml, is_log, read_gamma

SONY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<NonRealTimeMeta xmlns="urn:schemas-professionalDisc:nonRealTimeMeta:ver.2.20">
    <AcquisitionRecord>
        <Group name="CameraUnitMetadataSet">
            <Item name="CaptureColorPrimaries" value="s-gamut3-cine"/>
            <Item name="CaptureGammaEquation" value="s-log3-cine"/>
        </Group>
    </AcquisitionRecord>
</NonRealTimeMeta>
"""


def test_read_gamma_finds_gamma_even_when_it_is_not_first(tmp_path):
    xml_path = tmp_path / "clip.XML"
    xml_path.write_text(SONY_XML)
    assert read_gamma(xml_path) == "s-log3-cine"


def test_read_gamma_raises_error_when_gamma_is_missing(tmp_path):
    xml_path = tmp_path / "clip.XML"
    xml_path.write_text('<NonRealTimeMeta xmlns="urn:test"></NonRealTimeMeta>')
    with pytest.raises(ValueError):
        read_gamma(xml_path)


def test_find_sidecar_xml_finds_sony_m01_file(tmp_path):
    video_path = tmp_path / "C0001.MP4"
    video_path.touch()
    (tmp_path / "C0001M01.XML").touch()
    assert find_sidecar_xml(video_path) == tmp_path / "C0001M01.XML"


def test_find_sidecar_xml_returns_none_when_there_is_no_xml(tmp_path):
    video_path = tmp_path / "phone_clip.mov"
    video_path.touch()
    assert find_sidecar_xml(video_path) is None


@pytest.mark.parametrize(
    "gamma, expected",
    [
        ("s-log3-cine", True),
        ("s-log3", True),
        ("S-Log2", True),
        ("rec709", False),
        ("hlg", False),
        (None, False),
    ],
)
def test_is_log(gamma, expected):
    assert is_log(gamma) == expected