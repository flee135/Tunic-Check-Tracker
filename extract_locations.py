"""Download the list of all checks from the Tunic Randomizer repo and save it as locations.json.

locations.json groups the checks by the setting that adds them. Each group maps
"<id> [<scene>]" to "<area> - <check name>".
- "base": always in the game. The randomizer keeps these as a JSON string in src/Data/Locations.cs.
- "grass": added by grass shuffle. From src/Data/Grass.json, which lists grass by region.
  The scene comes from RegionDict in src/Patches/ERData.cs, and the area from
  SimplifiedSceneNames in src/Data/Locations.cs.
- "bells": added by bell shuffle. From BellLocationNames in src/Patches/BellShuffle.cs.
- "fuses": added by fuse shuffle. From src/Data/FuseDescriptions.json.
- "breakables": added by breakable shuffle. From src/Data/BreakableDescriptions.json.
- "enemy drops" and "extra enemy drops": added by enemy drop shuffle. From src/Data/EnemyData.json.
  Night and New Game+ enemies are the extra ones.
Re-run this after the randomizer updates.

Usage: python extract_locations.py <release tag>
For example: python extract_locations.py 5.0.2
"""
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

SOURCE_URL = "https://raw.githubusercontent.com/silent-destroyer/tunic-randomizer/{tag}/{path}"
# The C# line: public static string LocationNamesJson = "{...}";
LOCATION_NAMES_JSON_RE = re.compile(r'LocationNamesJson = ("(?:[^"\\]|\\.)*");')
# The C# dictionary: BellLocationNames = new Dictionary<string, string>() { {"<id>", "<name>"}, ... };
BELL_LOCATION_NAMES_RE = re.compile(r"BellLocationNames = new Dictionary<string, string>\(\) \{(.*?)\};", re.S)
DICT_ENTRY_RE = re.compile(r'\{\s*"([^"]+)",\s*"([^"]+)"\s*\}')
# The C# dictionary: SimplifiedSceneNames = new Dictionary<string, string>() { {"<scene>", "<area>"}, ... };
SIMPLIFIED_SCENE_NAMES_RE = re.compile(r"SimplifiedSceneNames = new Dictionary<string, string>\(\) \{(.*?)\};", re.S)
# The C# dictionary: RegionDict = new Dictionary<string, RegionInfo> { { "<region>", new RegionInfo("<scene>", ...) }, ... };
REGION_DICT_RE = re.compile(r"RegionDict = new Dictionary<string, RegionInfo> \{(.*?)\n\s*\};", re.S)
# Some entries have a // comment after the opening brace.
REGION_ENTRY_RE = re.compile(r'\{\s*(?://[^\n]*\s*)?"([^"]+)",\s*new RegionInfo\("([^"]+)"')
TRAILING_COMMA_RE = re.compile(r",(\s*[\]}])")


def download_source(tag: str, path: str) -> str:
    url = SOURCE_URL.format(tag=tag, path=path)
    try:
        with urllib.request.urlopen(url) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise SystemExit(f"Could not find {path} for tag '{tag}'. Check the tag name.")
        raise SystemExit(f"Download failed: {e}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Download failed: {e.reason}")


def find_location_json(source: str) -> dict:
    m = LOCATION_NAMES_JSON_RE.search(source)
    if not m:
        raise SystemExit("Could not find LocationNamesJson in Locations.cs.")
    # The C# string literal uses the same escapes as JSON, so decode it as a JSON string first.
    return json.loads(json.loads(m.group(1)))


def find_bell_locations(source: str) -> dict:
    m = BELL_LOCATION_NAMES_RE.search(source)
    if not m:
        raise SystemExit("Could not find BellLocationNames in BellShuffle.cs.")
    return dict(DICT_ENTRY_RE.findall(m.group(1)))


def find_enemy_locations(enemies: dict, extra: bool) -> dict:
    return {key: enemy["EnemyDescription"] for key, enemy in enemies.items()
            if (enemy["IsNightEnemy"] or enemy["IsNGPlusEnemy"]) == extra}


def find_dict(regex: re.Pattern, entry_regex: re.Pattern, source: str, name: str) -> dict:
    m = regex.search(source)
    if not m:
        raise SystemExit(f"Could not find {name}.")
    return dict(entry_regex.findall(m.group(1)))


def find_grass_locations(grass_json: str, er_data: str, locations_cs: str) -> dict:
    # Grass.json has trailing commas, which Python's json module rejects.
    grass = json.loads(TRAILING_COMMA_RE.sub(r"\1", grass_json))
    region_scenes = find_dict(REGION_DICT_RE, REGION_ENTRY_RE, er_data, "RegionDict in ERData.cs")
    scene_areas = find_dict(SIMPLIFIED_SCENE_NAMES_RE, DICT_ENTRY_RE, locations_cs,
                            "SimplifiedSceneNames in Locations.cs")
    locations = {}
    for region, grass_ids in grass.items():
        scene = region_scenes[region]
        for grass_id in grass_ids:
            name, position = grass_id.split("~")
            if "bush" in grass_id:
                name = name.replace("bush", "Bush")
            else:
                name = name.replace("grass", "Grass")
            locations[f"{grass_id} [{scene}]"] = f"{scene_areas[scene]} - {region} {name} {position}"
    return locations


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python extract_locations.py <release tag>")
    tag = sys.argv[1]
    locations_cs = download_source(tag, "src/Data/Locations.cs")
    enemies = json.loads(download_source(tag, "src/Data/EnemyData.json"))
    groups = {
        "base": find_location_json(locations_cs),
        "grass": find_grass_locations(download_source(tag, "src/Data/Grass.json"),
                                      download_source(tag, "src/Patches/ERData.cs"), locations_cs),
        "bells": find_bell_locations(download_source(tag, "src/Patches/BellShuffle.cs")),
        "fuses": json.loads(download_source(tag, "src/Data/FuseDescriptions.json")),
        "breakables": json.loads(download_source(tag, "src/Data/BreakableDescriptions.json")),
        "enemy drops": find_enemy_locations(enemies, extra=False),
        "extra enemy drops": find_enemy_locations(enemies, extra=True),
    }
    for group, locations in groups.items():
        if not locations:
            raise SystemExit(f"No locations found for '{group}'.")
        bad = [v for v in locations.values() if " - " not in v]
        if bad:
            raise SystemExit(f"Location names missing the ' - ' between area and check: {bad}")
    out = Path(__file__).with_name("locations.json")
    out.write_text(json.dumps(groups, indent=2, ensure_ascii=False), encoding="utf-8")
    counts = ", ".join(f"{len(locations)} {group}" for group, locations in groups.items())
    print(f"Wrote {counts} locations to {out}")


if __name__ == "__main__":
    main()
