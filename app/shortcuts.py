import os
import subprocess
import shutil
from pathlib import Path
import re
import sys
import shlex

# === XDG Base Directory Spec ===
XDG_CONFIG_HOME = Path(os.getenv('XDG_CONFIG_HOME', Path.home() / '.config'))
CONFIG_DIR = XDG_CONFIG_HOME / 'barrel'

XDG_DATA_HOME = Path(os.getenv('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
DATA_DIR = XDG_DATA_HOME / 'barrelr'

XDG_CACHE_HOME = Path(os.getenv('XDG_CACHE_HOME', Path.home() / '.cache'))
CACHE_DIR = XDG_CACHE_HOME / 'barrel'

HOME = os.path.expanduser("~")
SHORTCUTS_DIR = str(DATA_DIR / 'shortcuts')

def get_shortcut_details(path):
    """Parses a .desktop file and returns a dictionary with its details.
    Includes robust error handling for unreadable or corrupted files.
    """
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except (IOError, OSError, UnicodeDecodeError) as e:
        print(f"Error reading or decoding shortcut file '{path}': {e}", file=sys.stderr)
        return None # Return None to indicate failure to read/parse
    
    details = {}
    m = re.search(r'^Name=(.*)$', content, re.MULTILINE)
    details['name'] = m.group(1) if m else Path(path).stem
    
    m = re.search(r'^Exec=(.*)$', content, re.MULTILINE)
    exec_val = m.group(1) if m else ''
    details['exec'] = exec_val
    
    m = re.search(r'^Icon=(.*)$', content, re.MULTILINE)
    details['icon'] = m.group(1) if m else ''
    
    m = re.search(r'^Terminal=(.*)$', content, re.MULTILINE)
    details['terminal'] = (m.group(1).lower() == 'true') if m else False
    
    # --- New parsing logic ---
    try:
        parts = shlex.split(exec_val)
    except ValueError:
        parts = []

    target_path = ''
    # 1. Identify where 'main.py' is.
    main_py_index = -1
    for i, part in enumerate(parts):
        if part.endswith('main.py'):
            main_py_index = i
            break
            
    if main_py_index != -1:
        # We are in main.py mode
        # Iterate remaining args to find the first positional argument
        args_after_main = parts[main_py_index+1:]
        i = 0
        while i < len(args_after_main):
            arg = args_after_main[i]
            if arg.startswith('--'):
                if arg == '--wait':
                    i += 1
                elif arg in ['--template', '--runner', '--env', '--post-exec']:
                    i += 2
                else:
                    # Unknown flag, assume value
                    i += 2
            else:
                target_path = arg
                break
    else:
        # Fallback for legacy/other patterns
        m_target = re.search(r'"([^"]+)"\s+(--\w+.*)?$', exec_val)
        target_path = m_target.group(1) if m_target else ''

    details['executable_path'] = target_path

    # Template
    m_template = re.search(r'--template\s+((?:[^"\s]+)|(?:\"[^\"]+\"))', exec_val)
    details['template'] = (m_template.group(1).strip('"')) if m_template else ''

    # Runner (as override)
    m_runner = re.search(r'--runner\s+((?:[^"\s]+)|(?:\"[^\"]+\"))', exec_val)
    details['runner'] = (m_runner.group(1).strip('"')) if m_runner else ''
    
    # Env Vars (as override)
    m_env = re.search(r'--env\s+(.*?)(\s+--|$)', exec_val)
    if m_env:
        env_str = m_env.group(1).strip()
        details['env'] = shlex.split(env_str)
    else:
        details['env'] = []

    # Post-exec
    m_post = re.search(r'--post-exec\s+((?:[^"\s]+)|(?:\"[^\"]+\"))', exec_val)
    details['post_exec'] = (m_post.group(1).strip('"')) if m_post else ''

    return details

def update_shortcut(path, details):
    """Updates a .desktop file with the given details."""
    
    new_exec = details['exec']

    lines = [
        "[Desktop Entry]", 
        f"Name={details['new_name']}",
        f"Exec={new_exec}",
        f"Icon={details['icon']}",
        f"Terminal={'true' if details['terminal'] else 'false'}",
        "Type=Application"
    ]
    
    content_to_write = "\n".join(lines) + "\n"

    if details['new_name'] != details['name']:
        new_path = os.path.join(os.path.dirname(path), f"{details['new_name']}.desktop")
        if os.path.islink(new_path):
            try:
                os.remove(new_path)
            except OSError:
                pass
        with open(new_path, 'w') as f:
            f.write(content_to_write)
        os.chmod(new_path, 0o755)
        os.remove(path)

        old_link = os.path.join(details['desktop_dir'], f"{details['name']}.desktop")
        if os.path.lexists(old_link):
            os.remove(old_link)
        
        new_link = os.path.join(details['desktop_dir'], f"{details['new_name']}.desktop")
        try:
            if os.path.lexists(new_link):
                os.remove(new_link)
            os.symlink(new_path, new_link)
        except (OSError, NotImplementedError):
            shutil.copy2(new_path, new_link)
    else:
        if os.path.islink(path):
            try:
                os.remove(path)
            except OSError:
                pass
        with open(path, 'w') as f:
            f.write(content_to_write)
        os.chmod(path, 0o755)
        
        desktop_link = os.path.join(details['desktop_dir'], f"{details['name']}.desktop")
        try:
            if os.path.lexists(desktop_link):
                os.remove(desktop_link)
            os.symlink(path, desktop_link)
        except (OSError, NotImplementedError):
            shutil.copy2(path, desktop_link)

def run_shortcut(filename_or_path):
    path = filename_or_path
    if not os.path.isabs(path):
        desktop_dir = (
            os.path.join(HOME, "Desktop")
            if os.path.exists(os.path.join(HOME, "Desktop"))
            else HOME
        )
        path = os.path.join(desktop_dir, path)

    if not os.path.exists(path):
        print(f"Error: Shortcut file not found: {path}", file=sys.stderr)
        return

    details = get_shortcut_details(path)
    if details and details.get('exec'):
        try:
            # Prepare environment
            env = os.environ.copy()
            # If running from plain Termux, DISPLAY might be missing.
            # Default to :0 which is standard for Termux:X11
            if "DISPLAY" not in env:
                env["DISPLAY"] = ":0"
                # Try to launch Termux:X11 app automatically
                try:
                    subprocess.run(
                        ["am", "start", "-n", "com.termux.x11/com.termux.x11.MainActivity"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                except Exception:
                    pass

            # shell=True allows execution of complex command strings found in Exec=
            # We use setsid to create a new process group, making it easier to kill the whole tree later
            return subprocess.Popen(details['exec'], shell=True, start_new_session=True, env=env)
        except Exception as e:
            print(f"Error executing shortcut '{path}': {e}", file=sys.stderr)
            return None
    else:
        print(f"Error: Could not parse 'Exec' command from {path}", file=sys.stderr)
        return None
def delete_shortcut(filename):
    # — 1) .desktop from Applications —
    xdg = Path(os.getenv('XDG_DATA_HOME', Path.home()/'.local'/'share'))
    apps_dir = xdg/'applications' / 'shortcuts'
    desktop_file = apps_dir/filename
    if desktop_file.exists():
        desktop_file.unlink()

    # — 2) symlink from Desktop —
    desk = Path.home()/'Desktop'
    link = desk/filename
    if link.is_symlink() or link.exists():
        link.unlink()

    # — 3) icon from global theme —
    icon_base = Path(filename).stem
    icons_dir = xdg/'icons'/'hicolor'/'48x48'/'apps'
    for ext in ('.png','.svg','.ico','.xpm'):
        ico = icons_dir/f"{icon_base}{ext}"
        if ico.exists():
            ico.unlink()

def create_shortcut_common(
    preselected_path,
    ask_string_cb,
    ask_file_cb,
    show_warning_cb,
    show_info_cb,
    extract_exe_icon_cb,
    refresh_shortcuts_cb,
    HOME,
    # New parameters for customization
    template_name=None,
    runner=None, # As override
    env=None, # As override
    post_exec_cmd=None
):
    # 1. Ask for name and path
    if preselected_path:
        default_name = Path(preselected_path).stem
        name = ask_string_cb("Name", "Shortcut name:", default_name)
        path = preselected_path
    else:
        name = ask_string_cb("Name", "Shortcut name:")
        path = ask_file_cb("Choose file/script")

    if not name or " " in name or not path:
        show_warning_cb("Warning", "Name cannot contain spaces and you must select a file!")
        return

    # 2. Build exec command using the new main.py entrypoint
    final_post_exec_cmd = post_exec_cmd
    if template_name:
        from . import templates
        template_data = templates.get_template(template_name)
        if template_data and template_data.get("post_exec") and final_post_exec_cmd is None:
            final_post_exec_cmd = template_data.get("post_exec")

    python_executable = sys.executable
    main_script_path = Path(__file__).parent.absolute() / 'main.py'
    
    cmd_parts = [
        f'"{python_executable}"',
        f'"{main_script_path}"'
    ]

    if template_name:
        cmd_parts.append(f'--template "{template_name}"')

    if runner:
        cmd_parts.append(f'--runner "{runner}"')
        
    if env:
        quoted_env = [shlex.quote(e) for e in env]
        cmd_parts.append(f'--env {" ".join(quoted_env)}')

    if final_post_exec_cmd:
        cmd_parts.append(f'--post-exec "{final_post_exec_cmd}"')
        
    # Target path must be last before options that are part of main.py
    cmd_parts.append(f'"{path}"')
    cmd_parts.append('--wait')
    
    exec_cmd = " ".join(cmd_parts)


    # 3. Prepare icon directories
    icons_cache = CACHE_DIR / 'icons'
    icons_data = XDG_DATA_HOME / 'icons' / 'hicolor' / '48x48' / 'apps'
    icons_cache.mkdir(parents=True, exist_ok=True)
    icons_data.mkdir(parents=True, exist_ok=True)

    # 4. Extract icon from EXE or prompt for one
    icon_path = "application-x-executable"
    if path.lower().endswith('.exe'):
        tmpico = icons_data / f"{Path(path).stem}.png"
        if extract_exe_icon_cb(path, str(tmpico)):
            icon_path = str(tmpico)
        else:
            chosen = ask_file_cb(
                "Selectează o iconiță (opțional)",
                initial_dir=str(icons_data),
                initial_file=tmpico.name,
                file_types=[("Imagini", "*.png *.svg *.ico *.xpm")]
            )
            if chosen:
                icon_path = chosen

    used_icon = icon_path

    # 5. Build and save .desktop file
    details = {
        'name': name,
        'new_name': name,
        'exec': exec_cmd,
        'icon': used_icon,
        'terminal': True, # Keep terminal true for the 'press enter' message
        'executable_path': path,
        'desktop_dir': str(Path(HOME) / "Desktop"),
        'template': template_name,
        'runner': runner,
        'env': env,
        'post_exec': post_exec_cmd
    }
    
    apps_dir = XDG_DATA_HOME / 'applications' / 'shortcuts'
    apps_dir.mkdir(parents=True, exist_ok=True)
    desktop_file = apps_dir / f"{name}.desktop"
    
    update_shortcut(str(desktop_file), details)

    show_info_cb("Success", f"Shortcut created and on Desktop:\n{desktop_file}")
    refresh_shortcuts_cb()