# Tunic Check Tracker

A check tracker for the [TUNIC Randomizer](https://github.com/silent-destroyer/tunic-randomizer).
It reads the game's log while you play and ticks off each check as you collect it.

## Download

1. Go to the [Releases](https://github.com/flee135/Tunic-Check-Tracker/releases) page.
2. Download the latest `TunicCheckTracker-<version>.zip`.
3. Unzip it anywhere.
4. Run `TunicCheckTracker.exe` inside that folder.

No Python or other installs are needed.

## Setup

You need TUNIC with the Tunic Randomizer mod installed. The mod uses BepInEx, which writes the log
the tracker reads.

1. Start the tracker.
2. Go to **Settings > Select Log File**.
3. Pick `LogOutput.log` in your TUNIC `BepInEx` folder. For a Steam install this is usually
   `C:\Program Files (x86)\Steam\steamapps\common\TUNIC\BepInEx\LogOutput.log`.

The tracker remembers your choice in `settings.json`, next to the exe.

You can open the tracker before or after starting the game.

## Known Issues

- **Progress is lost when the game restarts.** The tracker only knows what's in the current log.
  BepInEx starts a fresh `LogOutput.log` each time TUNIC launches, so checks from earlier sessions
  are gone. If you close the game and continue the same file later, the tracker starts from zero.

## Run from source

You need Python 3.10 or newer. Nothing else needs installing.

```
python tracker.py
```

You can also pass the log path directly:

```
python tracker.py "path\to\LogOutput.log"
```

## Updating the check list

`locations.json` comes from the [Tunic Randomizer repo](https://github.com/silent-destroyer/tunic-randomizer).
After the randomizer updates, run this with the new release tag to rebuild it:

```
python extract_locations.py 5.0.2
```

## Credits

The check list comes from [Tunic Randomizer](https://github.com/silent-destroyer/tunic-randomizer)
by silentdestroyer. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## License

[MIT](LICENSE)
