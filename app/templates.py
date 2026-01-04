import os
import json
from pathlib import Path

# Use XDG_CONFIG_HOME for storing user-editable templates
XDG_CONFIG_HOME = Path(os.getenv('XDG_CONFIG_HOME', Path.home() / '.config'))
CONFIG_DIR = XDG_CONFIG_HOME / 'barrel'
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_FILE = CONFIG_DIR / 'templates.json'

def get_default_templates():
    """
    Provides a default set of templates if the user's file doesn't exist.
    This gives the user a starting point with common presets.
    """
    return {
        "Default (no runner)": {
            "runner": "",
            "env": [],
            "description": "Runs the executable directly. Good for scripts."
        },
        "Hangover-BOX64 (default)": {
            "runner": "hangover-wine",
            "env": [],
            "description": "Runs with the standard 'wine' command."
        },
        "Hangover-BOX64 (DXVK HUD)": {
            "runner": "hangover-wine",
            "env": ["DXVK_HUD=1"],
            "description": "Runs with Wine and enables the DXVK performance HUD."
        },
        "Hangover-FEX (default)": {
            "runner": "hangover-wine",
            "emulator": "FEX",
            "env": [],
            "description": "Runs with a 'proton' command if available in PATH."
        }
    }

def load_templates():
    """
    Loads templates from the JSON file.
    If the file doesn't exist, it creates it with default values.
    """
    if not TEMPLATES_FILE.exists():
        templates = get_default_templates()
        save_templates(templates)
        return templates
    
    try:
        with open(TEMPLATES_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        # If the file is corrupted or unreadable, fall back to defaults
        return get_default_templates()

def save_templates(templates_dict):
    """Saves the given dictionary of templates to the JSON file."""
    try:
        with open(TEMPLATES_FILE, 'w') as f:
            json.dump(templates_dict, f, indent=4)
        return True
    except IOError:
        return False

def get_template(template_name):
    """Retrieves a single template by name."""
    templates = load_templates()
    return templates.get(template_name)

def delete_template(template_name):
    """Deletes a template by name."""
    templates = load_templates()
    if template_name in templates:
        del templates[template_name]
        return save_templates(templates)
    return False
