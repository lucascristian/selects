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