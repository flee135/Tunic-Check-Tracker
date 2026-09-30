"""Download the list of all checks from the Tunic Randomizer repo and save it as locations.json.

The randomizer keeps its location list as a JSON string in src/Data/Locations.cs, mapping
"<id> [<scene>]" to "<area> - <check name>". Re-run this after the randomizer updates.

Usage: python extract_locations.py <release tag>
For example: python extract_locations.py 5.0.2
"""
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

SOURCE_URL = "https://raw.githubusercontent.com/silent-destroyer/tunic-randomizer/{tag}/src/Data/Locations.cs"
# The C# line: public static string LocationNamesJson = "{...}";
LOCATION_NAMES_JSON_RE = re.compile(r'LocationNamesJson = ("(?:[^"\\]|\\.)*");')


def download_source(tag: str) -> str:
    url = SOURCE_URL.format(tag=tag)
    try:
        with urllib.request.urlopen(url) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise SystemExit(f"Could not find Locations.cs for tag '{tag}'. Check the tag name.")
        raise SystemExit(f"Download failed: {e}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Download failed: {e.reason}")


def find_location_json(source: str) -> dict:
    m = LOCATION_NAMES_JSON_RE.search(source)
    if not m:
        raise SystemExit("Could not find LocationNamesJson in Locations.cs.")
    # The C# string literal uses the same escapes as JSON, so decode it as a JSON string first.
    return json.loads(json.loads(m.group(1)))


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python extract_locations.py <release tag>")
    locations = find_location_json(download_source(sys.argv[1]))
    bad = [v for v in locations.values() if " - " not in v]
    if bad:
        raise SystemExit(f"Location names missing the ' - ' between area and check: {bad}")
    out = Path(__file__).with_name("locations.json")
    out.write_text(json.dumps(locations, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(locations)} locations to {out}")


if __name__ == "__main__":
    main()
