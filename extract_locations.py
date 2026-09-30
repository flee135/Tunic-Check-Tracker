"""Pull the list of all checks out of TunicRandomizer.dll and save it as locations.json.

The randomizer stores its location list as a JSON string inside the DLL, mapping
"<id> [<scene>]" to "<area> - <check name>". Re-run this after updating the randomizer.

Usage: python extract_locations.py path\\to\\TunicRandomizer.dll
"""
import json
import re
import sys
from pathlib import Path

# A check that is always in the list, used to find the right JSON object.
ANCHOR = '"19 [Sword Cave]":"Stick House - Stick Chest"'


def find_location_json(data: bytes) -> dict:
    # .NET stores string literals as UTF-16. Try both byte alignments.
    for offset in (0, 1):
        text = data[offset:].decode("utf-16-le", errors="replace")
        i = text.find(ANCHOR)
        if i == -1:
            continue
        start = text.rfind("{", 0, i)
        end = text.find("}", i)
        return json.loads(text[start:end + 1])
    raise SystemExit("Could not find the location list in the DLL.")


def main():
    if len(sys.argv) != 2:
        raise SystemExit(r"Usage: python extract_locations.py path\to\TunicRandomizer.dll")
    dll = Path(sys.argv[1])
    if not dll.is_file():
        raise SystemExit(f"File not found: {dll}")
    locations = find_location_json(dll.read_bytes())
    bad = [k for k in locations if re.search(r" - ", k)]
    if bad:
        raise SystemExit(f"Unexpected location keys containing ' - ': {bad}")
    out = Path(__file__).with_name("locations.json")
    out.write_text(json.dumps(locations, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(locations)} locations to {out}")


if __name__ == "__main__":
    main()
