import os
import shutil
import sys
from pathlib import Path
from . import shortcuts
from . import templates
from . import config

class ViewController:
    def __init__(self):
        self.HOME = os.path.expanduser("~")
        self.XDG_DATA_HOME = Path(os.getenv('XDG_DATA_HOME', Path.home()/'.local'/'share'))

    def get_shortcuts_data(self):
        """
        Returns a sorted list of dictionaries for the UI.
        Each dict contains: {'name', 'path', 'template', 'details_obj'}
        """
        apps_dir = self.XDG_DATA_HOME / 'applications' / 'shortcuts'
        apps_dir.mkdir(parents=True, exist_ok=True)
        
        items = []
        if not apps_dir.exists():
            return items

        # List all .desktop files
        files = [f for f in os.listdir(apps_dir) if f.endswith(".desktop")]
        
        for filename in files:
            full_path = apps_dir / filename
            # Use the shared parser
            details = shortcuts.get_shortcut_details(str(full_path))
            
            if details:
                items.append({
                    'filename': filename,
                    'path': str(full_path),
                    'name': details.get('name', filename),
                    'template': details.get('template', 'No Template'),
                    'raw_details': details
                })
        
        # Sort by name
        items.sort(key=lambda x: x['name'].lower())
        return items

    def get_templates_data(self):
        """
        Returns a dictionary of templates, or a sorted list of tuples if needed by UI.
        """
        return templates.load_templates()

    def get_prefixes_data(self):
        """
        Returns a list of prefix paths.
        """
        return config.load_prefixes()

    def get_available_runners(self):
        """
        Centralized logic to find available runners (wine, proton, etc.)
        """
        found_runners = []
        # Priority order
        candidates = ["proton", "wine", "wine-stable", "hangover-wine", "proton-wine", "bash"]
        
        for runner in candidates:
            if shutil.which(runner):
                found_runners.append(runner)
        
        return found_runners or ["bash"]

    def get_template_form_defaults(self):
        """
        Returns default values for creating a new template.
        """
        from . import actions # Import here to avoid circular dependency issues if any
        return {
            "runner": "hangover-wine",
            "runner": "hangover-wine",
            "env": [
                f"WINEPREFIX={Path.home() / '.wine'}",
                f"VK_ICD_FILENAMES={actions.VK_MAP.get('Freedreno', '')}"
            ],
            "description": "Default settings for Hangover+Freedreno", 
            "post_exec": ""
        }

    def get_template_ui_schema(self):
        """
        Defines the form structure for the Template Editor.
        UI implementations (X11, Native) should iterate this to build the view.
        """
        from . import actions
        
        return [
            {
                "section": "Basic Info",
                "fields": [
                    {"key": "description", "label": "Description", "type": "text"},
                    {"key": "runner", "label": "Runner", "type": "combo", "options": self.get_available_runners()},
                ]
            },
            {
                "section": "System Options",
                "fields": [
                    # Special field: The UI should handle 'env_manager' specifically, 
                    # as it involves multiple dropdowns (DXVK, VK, FEX) resolving to the 'env' list.
                    {"key": "env", "type": "env_manager"} 
                ]
            },
            {
                "section": "Post-Execution",
                "fields": [
                    {"key": "post_exec", "label": "Command to run after exit", "type": "text"},
                    {
                        "key": "parallel_cmd", 
                        "label": "Kill services.exe (background)", 
                        "type": "checkbox_mapped",
                        "on_value": "sleep 1; pkill -f services.exe",
                        "off_value": ""
                    }
                ]
            }
        ]
