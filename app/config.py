import json
import os
from pathlib import Path

# === XDG Base Directory Spec ===
XDG_CONFIG_HOME = Path(os.getenv('XDG_CONFIG_HOME', Path.home() / '.config'))
CONFIG_DIR = XDG_CONFIG_HOME / 'barrel'
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

PREFIXES_FILE = CONFIG_DIR / 'wine_prefixes.json'
SETTINGS_FILE = CONFIG_DIR / 'settings.json'

# Repository URLs
TEMPLATE_REPO = "https://github.com/moio9/barrel"
APP_REPO = "https://github.com/moio9/barrel"

def load_settings():
    if not SETTINGS_FILE.exists():
        return {}
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)

def get_setting(key, default=None):
    s = load_settings()
    return s.get(key, default)

def set_setting(key, value):
    s = load_settings()
    s[key] = value
    save_settings(s)

# --- Last Commit Hash for non-git updates ---
LAST_COMMIT_FILE = CONFIG_DIR / 'last_update_commit.txt'

def read_last_commit_hash():
    if not LAST_COMMIT_FILE.exists():
        return None
    try:
        with open(LAST_COMMIT_FILE, "r") as f:
            return f.read().strip()
    except OSError:
        return None

def write_last_commit_hash(commit_hash):
    try:
        with open(LAST_COMMIT_FILE, "w") as f:
            f.write(commit_hash)
        return True
    except OSError:
        return False

def load_prefixes():
    if not PREFIXES_FILE.exists():
        return []
    with open(PREFIXES_FILE, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return []

    # Migration: Convert list of strings to list of dicts
    if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], str):
        new_data = []
        for path in data:
            name = os.path.basename(path)
            if not name: # Handle root or empty paths
                 name = path
            new_data.append({"name": name, "path": path})
        save_prefixes(new_data)
        return new_data
        
    return data

def save_prefixes(prefixes):
    with open(PREFIXES_FILE, "w") as f:
        json.dump(prefixes, f, indent=4)
