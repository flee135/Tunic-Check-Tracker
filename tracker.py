"""Tunic Randomizer check tracker.

Tails the BepInEx log and marks off checks as the player collects them.
- "Starting new single player file with seed: N" resets the tracker.
- "Loading single player seed: <settings string>" gives the seed and which shuffles are on.
- "Picked up item <key> (<item>)" marks that check as done.
- "Entering scene <scene> (<n>)" moves that scene's checks to the top of the list.

Usage: python tracker.py [path\\to\\LogOutput.log]
Pick the log from Settings > Select Log File. The choice is saved in settings.json.
"""
import base64
import ctypes
import json
import re
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

APP_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
SETTINGS_FILE = APP_DIR / "settings.json"
NEW_FILE = "Starting new single player file with seed: "
# Logged every time a save loads, new or continued. See parse_seed_settings.
LOAD_SEED = "Loading single player seed: "
# The randomizer version SHUFFLE_BITS and locations.json come from.
RANDOMIZER_VERSION = "5.0.2"
# Bit positions in the settings string's logic flags (RandomizerSettings.logicSettings in the
# randomizer).
SHUFFLE_BITS = {
    "grass": 11,
    "breakables": 16,
    "fuses": 17,
    "bells": 18,
    "enemy drops": 22,
    "extra enemy drops": 23,
}
# Shuffles whose checks are in locations.json.
SUPPORTED_SHUFFLES = set()
# "Picked up item <id> [<scene>] (<item>)". The item name can contain brackets and
# parentheses, so stop at the first "] (".
PICKUP_RE = re.compile(r"Picked up item (.*?\]) \(")
# "Entering scene <scene name> (<scene number>)"
SCENE_RE = re.compile(r"Entering scene (.*) \(\d+\)")
POLL_MS = 1000
THEMES = {
    "light": {"bg": "#f0f0f0", "fg": "#000000", "field": "#ffffff", "button": "#e1e1e1",
              "active": "#d4d4d4", "border": "#adadad", "done": "#999999", "area_done": "#2e8b57",
              "thumb": "#c1c1c1", "thumb_active": "#a6a6a6", "warn": "#b35900"},
    "dark": {"bg": "#202020", "fg": "#e6e6e6", "field": "#2b2b2b", "button": "#333333",
             "active": "#454545", "border": "#3c3c3c", "done": "#7a7a7a", "area_done": "#5cc98a",
             "thumb": "#5a5a5a", "thumb_active": "#707070", "warn": "#f0a848"},
}


class LogTail:
    """Reads new lines from a file that keeps growing. Starts over if the file is replaced."""

    def __init__(self, path: Path):
        self.path = path
        self.pos = 0
        self.partial = b""

    def read_new_lines(self):
        """Returns (restarted, lines). restarted is True when reading from the top again."""
        try:
            size = self.path.stat().st_size
        except FileNotFoundError:
            return False, []
        restarted = False
        if size < self.pos:
            # The game restarted and began a fresh log.
            self.pos, self.partial = 0, b""
            restarted = True
        if size == self.pos:
            return restarted, []
        with open(self.path, "rb") as f:
            f.seek(self.pos)
            data = f.read()
        self.pos += len(data)
        chunks = (self.partial + data).split(b"\n")
        self.partial = chunks.pop()  # last piece may be an unfinished line
        return restarted, [c.decode("utf-8", errors="replace").rstrip("\r") for c in chunks]


class Tracker:
    def __init__(self, root: tk.Tk, log_path: Path | None, locations: dict):
        self.root = root
        # None until the player picks a log file.
        self.tail = LogTail(log_path) if log_path else None
        # area -> list of (key, check name), in list order
        self.areas = {}
        # scene name from the log -> area header. Each area is exactly one scene.
        self.scene_areas = {}
        for key, full_name in locations.items():
            area, name = full_name.split(" - ", 1)
            self.areas.setdefault(area, []).append((key, name))
            self.scene_areas[key[key.rindex("[") + 1:-1]] = area
        self.known = set(locations)
        self.done = set()
        self.seed = None
        self.version = None
        self.shuffles = set()
        self.scene = None
        self.scene_changed = False
        self.open_areas = set()
        self.dirty = True

        root.title("Tunic Check Tracker")
        root.geometry("460x720")

        settings = load_settings()
        self.dark_mode = tk.BooleanVar(value=settings.get("dark_mode", False))
        self.on_top = tk.BooleanVar(value=settings.get("always_on_top", False))
        root.attributes("-topmost", self.on_top.get())
        menubar = tk.Menu(root)
        settings_menu = tk.Menu(menubar, tearoff=False)
        settings_menu.add_command(label="Select Log File...", command=self.change_log)
        settings_menu.add_checkbutton(label="Dark mode", variable=self.dark_mode,
                                      command=self.toggle_dark_mode)
        settings_menu.add_checkbutton(label="Always on top", variable=self.on_top,
                                      command=self.toggle_on_top)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        root.config(menu=menubar)

        # Shown above the status only when the seed's randomizer version isn't RANDOMIZER_VERSION.
        self.warning = ttk.Label(root, font=("Segoe UI", 10, "bold"), padding=(6, 6, 6, 0), wraplength=440)
        self.status = ttk.Label(root, font=("Segoe UI", 11, "bold"), padding=(6, 6, 6, 0), wraplength=440)
        self.status.pack(fill="x")
        controls = ttk.Frame(root, padding=6)
        controls.pack(fill="x")
        ttk.Button(controls, text="Expand all", command=lambda: self.set_all_open(True)).pack(side="left")
        ttk.Button(controls, text="Collapse all", command=lambda: self.set_all_open(False)).pack(side="left", padx=(6, 0))
        self.hide_done = tk.BooleanVar(value=settings.get("hide_done", False))
        ttk.Checkbutton(controls, text="Hide completed", variable=self.hide_done,
                        command=self.toggle_hide_done).pack(side="right")

        frame = ttk.Frame(root)
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, show="tree", selectmode="none")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.tag_configure("area", font=("Segoe UI", 10, "bold"))
        self.tree.tag_configure("area_done", font=("Segoe UI", 10, "bold"))
        self.tree.bind("<Button-1>", self.on_click)

        self.apply_theme()
        self.poll()

    def apply_theme(self):
        dark = self.dark_mode.get()
        c = THEMES["dark" if dark else "light"]
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=c["bg"], foreground=c["fg"], fieldbackground=c["field"],
                        bordercolor=c["border"], lightcolor=c["bg"], darkcolor=c["bg"],
                        troughcolor=c["bg"], arrowcolor=c["fg"], focuscolor=c["fg"])
        style.map(".", background=[("disabled", c["bg"]), ("active", c["active"])])
        style.configure("TButton", background=c["button"])
        style.map("TButton", background=[("pressed", c["border"]), ("active", c["active"])])
        style.configure("TCheckbutton", indicatorbackground=c["field"], indicatorforeground=c["fg"])
        style.map("TCheckbutton", background=[("active", c["bg"])],
                  indicatorbackground=[("pressed", c["active"]), ("active", c["field"])])
        style.configure("Treeview", background=c["field"], fieldbackground=c["field"], foreground=c["fg"])
        style.configure("TScrollbar", background=c["thumb"])
        style.map("TScrollbar", background=[("active", c["thumb_active"])])
        self.tree.tag_configure("area_done", foreground=c["area_done"])
        self.tree.tag_configure("done", foreground=c["done"])
        self.warning.configure(foreground=c["warn"])
        self.root.configure(bg=c["bg"])
        set_title_bar_dark(self.root, dark)

    def toggle_dark_mode(self):
        save_setting("dark_mode", self.dark_mode.get())
        self.apply_theme()

    def toggle_on_top(self):
        save_setting("always_on_top", self.on_top.get())
        self.root.attributes("-topmost", self.on_top.get())

    def on_click(self, event):
        """Clicking a check toggles it between done and not done."""
        row = self.tree.identify_row(event.y)
        # Check rows use the check's key as their id. Area headers and the spacer have no parent.
        if not row or not self.tree.parent(row):
            return
        if row in self.done:
            self.done.discard(row)
        else:
            self.done.add(row)
        self.mark_dirty()

    def toggle_hide_done(self):
        save_setting("hide_done", self.hide_done.get())
        self.mark_dirty()

    def change_log(self):
        path = ask_log_path(self.root)
        if not path:
            return
        save_setting("log_path", str(path))
        self.tail = LogTail(path)
        self.reset()
        self.scene = None
        self.redraw()

    def set_all_open(self, is_open: bool):
        self.open_areas = set(self.areas) if is_open else set()
        for area in self.tree.get_children():
            self.tree.item(area, open=is_open)

    def mark_dirty(self):
        self.dirty = True
        self.redraw()

    def reset(self, seed=None):
        self.done.clear()
        self.seed = seed
        self.version = None
        self.shuffles = set()
        self.dirty = True

    def handle_line(self, line: str):
        if NEW_FILE in line:
            self.reset(line.split(NEW_FILE, 1)[1].strip())
        elif LOAD_SEED in line:
            parsed = parse_seed_settings(line.split(LOAD_SEED, 1)[1].strip())
            if parsed:
                version, seed, shuffles = parsed
                if seed != self.seed:
                    self.reset(seed)
                self.version = version
                self.shuffles = shuffles
                self.dirty = True
        elif m := PICKUP_RE.search(line):
            self.mark(m.group(1))
        elif m := SCENE_RE.search(line):
            if m.group(1) != self.scene:
                self.scene = m.group(1)
                self.scene_changed = True
                self.dirty = True

    def mark(self, key: str):
        if key not in self.known:
            # Not in the main list (e.g. grass or breakables). Show it anyway.
            self.known.add(key)
            self.areas.setdefault("Other", []).append((key, key))
        if key not in self.done:
            self.done.add(key)
            self.dirty = True

    def poll(self):
        if self.tail:
            restarted, lines = self.tail.read_new_lines()
            if restarted:
                self.reset()
                self.scene = None
            for line in lines:
                self.handle_line(line)
        self.redraw()
        self.root.after(POLL_MS, self.poll)

    def redraw(self):
        if not self.dirty:
            return
        self.dirty = False
        if not self.tail:
            # Keep the list empty until there's a log to read.
            self.status.config(text="Go to Settings > Select Log File and choose LogOutput.log "
                                     "in your TUNIC/BepInEx folder to start tracking.")
            self.tree.delete(*self.tree.get_children())
            return
        total =sum(len(c) for c in self.areas.values())
        seed = f"Seed {self.seed}  —  " if self.seed else ""
        status = f"{seed}{len(self.done)} / {total} checks"
        supported = [s for s in SHUFFLE_BITS if s in self.shuffles and s in SUPPORTED_SHUFFLES]
        unsupported = [s for s in SHUFFLE_BITS if s in self.shuffles and s not in SUPPORTED_SHUFFLES]
        if supported:
            status += "\nShuffled: " + ", ".join(supported)
        self.status.config(text=status)
        warnings = []
        if self.version and self.version != RANDOMIZER_VERSION:
            warnings.append(f"⚠ This seed uses randomizer {self.version}, but the tracker is made "
                            f"for {RANDOMIZER_VERSION}. The settings and checks may be incorrect.")
        if unsupported:
            warnings.append("⚠ The following settings are on, but not supported: " + ", ".join(unsupported))
        if warnings:
            self.warning.config(text="\n".join(warnings))
            self.warning.pack(fill="x", before=self.status)
        else:
            self.warning.pack_forget()
        # Scenes with no checks (like the Windmill) have no area.
        current = self.scene_areas.get(self.scene)

        scroll_pos = self.tree.yview()[0]
        # Remember which areas the player opened, so the redraw keeps them open.
        for area in self.tree.get_children():
            if self.tree.item(area, "open"):
                self.open_areas.add(area)
            else:
                self.open_areas.discard(area)
        if self.scene_changed:
            # Show the new scene's checks: open its area and scroll up to it.
            self.scene_changed = False
            if current:
                self.open_areas.add(current)
                scroll_pos = 0
        self.tree.delete(*self.tree.get_children())
        hide = self.hide_done.get()
        # The current scene's area goes first, then the rest in their usual order.
        order = sorted(self.areas, key=lambda a: a != current)
        for area in order:
            checks = self.areas[area]
            got = sum(1 for k, _ in checks if k in self.done)
            # Keep the current scene's header even when it's done, so it's easy to confirm.
            if hide and got == len(checks) and area != current:
                continue
            tag = "area_done" if got == len(checks) else "area"
            self.tree.insert("", "end", iid=area, text=f"{area}  ({got}/{len(checks)})",
                             open=area in self.open_areas, tags=(tag,))
            for key, name in checks:
                is_done = key in self.done
                if hide and is_done:
                    continue
                mark = "✔" if is_done else "☐"
                self.tree.insert(area, "end", iid=key, text=f"{mark}  {name}",
                                 tags=("done",) if is_done else ())
            if area == current:
                # A blank row to separate the current scene from the rest.
                self.tree.insert("", "end", text="")
        self.tree.yview_moveto(scroll_pos)


def parse_seed_settings(text: str) -> tuple[str, str, set[str]] | None:
    """Reads the randomizer's settings string: "tunc:<version>:<seed>:<base64 settings>".

    The base64 part decodes to ":"-separated fields. Field 8 is a number whose bits are the
    logic settings. Returns (version, seed, names of the shuffles that are on), or None if the
    string isn't a settings string. If only the settings can't be decoded (for example, another
    randomizer version changed the format), the shuffles come back empty.
    """
    parts = text.split(":", 3)
    if len(parts) != 4 or parts[0] != "tunc":
        return None
    try:
        fields = base64.b64decode(parts[3]).decode("utf-8").split(":")
        logic = int(fields[8])
    except (ValueError, IndexError):
        logic = 0
    return parts[1], parts[2], {name for name, bit in SHUFFLE_BITS.items() if logic >> bit & 1}


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_setting(key: str, value):
    settings = load_settings()
    settings[key] = value
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def set_title_bar_dark(root: tk.Tk, dark: bool):
    """Asks Windows to draw the title bar dark or light. Does nothing on other systems."""
    if sys.platform != "win32":
        return
    root.update_idletasks()
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    value = ctypes.c_int(dark)
    # Attribute 20 is dark mode. Windows 10 before version 20H1 uses 19 instead.
    for attr in (20, 19):
        if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
            break


def ask_log_path(parent):
    """Shows a file picker for the BepInEx log. Returns None if the player cancels."""
    path = filedialog.askopenfilename(
        parent=parent,
        title=r"Select LogOutput.log (in the TUNIC\BepInEx folder)",
        initialfile="LogOutput.log",
        filetypes=[("Log files", "*.log"), ("All files", "*.*")],
    )
    return Path(path) if path else None


def main():
    locations_file = Path(__file__).with_name("locations.json")
    locations = json.loads(locations_file.read_text(encoding="utf-8"))
    saved_path = load_settings().get("log_path")
    log_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(saved_path) if saved_path else None
    root = tk.Tk()
    Tracker(root, log_path, locations)
    root.mainloop()


if __name__ == "__main__":
    main()
