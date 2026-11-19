"""Read Sony camera metadata from the XML file saved next to each clip."""

import xml.etree.ElementTree as ET
from pathlib import Path


def read_gamma(xml_path: Path) -> str:
    """Return the gamma curve the clip was filmed with, e.g. "s-log3-cine"."""
    root = ET.parse(xml_path).getroot()
    for item in root.findall(".//{*}Item"):
        if item.get("name") == "CaptureGammaEquation":
            return item.get("value")
    raise ValueError("No gamma information found")


def find_sidecar_xml(video_path: Path) -> Path | None:
    """Return the Sony XML file saved next to a clip, or None if there is none.

    Sony names it after the clip with "M01" added: C0001.MP4 -> C0001M01.XML.
    """
    candidate = video_path.with_name(video_path.stem + "M01.XML")
    if candidate.exists():
        return candidate
    return None


def is_log(gamma: str | None) -> bool:
    """Return True if the gamma curve is a Sony log curve such as S-Log3."""
    if gamma is None:
        return False
    return gamma.lower().startswith("s-log")
