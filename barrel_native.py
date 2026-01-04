#!/data/data/com.termux/files/usr/bin/env python3

import sys
import os
import shutil
import subprocess
import termuxgui as tg
import time
import threading
import json
import re
import requests
import glob
import tempfile
import tarfile
import urllib.request
import traceback
from pathlib import Path

# Local imports
from app import __version__, __app_name__
from app import config
from app import shortcuts
from app import templates
from app import installers
from app import actions
from app import view_controller
from app import updater
from app import shortcuts
from app import templates
from app import updater
from app import installers
from app import view_controller

class FileExplorer:
    def __init__(self, conn, select_file=False, start_dir=None):
        self.conn = conn
        self.dialog = tg.Activity(conn, dialog=True)
        self.entries = []
        self.paths = []
        # Build UI
        root = tg.LinearLayout(self.dialog)
        tg.TextView(self.dialog, 'Select file or folder', root).setmargin(5)
        self.tree_scroll = tg.NestedScrollView(self.dialog, root)
        self.tree = tg.LinearLayout(self.dialog, self.tree_scroll, vertical=True)
        # Start directory
        self.start_dir    = start_dir or os.getenv('HOME')
        self.cwd          = self.start_dir
        self.select_file  = select_file
        self.selected_path = None
        self._load_dir(self.cwd)

    def _load_dir(self, directory):
        try:
            self.cwd = directory
            self.tree.clearchildren()
            self.entries.clear()
            self.paths.clear()

            # If we can select folders, add a "." entry
            if self.select_file:
                self._add_item('.', directory)

            # Add parent
            if directory != "/":
                parent = os.path.dirname(directory.rstrip('/'))
                self._add_item('..', parent)

            # Folder content
            for name in sorted(os.listdir(directory)):
                full_path = os.path.join(directory, name)
                self._add_item(name, full_path)
        except (PermissionError, FileNotFoundError):
            self._load_dir(os.getenv('HOME'))


    def _add_item(self, label, path):
        tv = tg.TextView(self.dialog, label, self.tree)
        tv.sendclickevent(True)
        tv.setmargin(8)
        tv.setheight(tg.View.WRAP_CONTENT)
        self.entries.append(tv)
        self.paths.append(path)

    def run(self):
        """Run the file explorer modal dialog"""
        for ev in self.conn.events():
            # If the dialog is destroyed, return None
            if ev.type == tg.Event.destroy and ev.value.get('aid') == self.dialog.aid:
                return None

            if ev.type == tg.Event.click:
                try:
                    idx = self.entries.index(ev.value['id'])
                    path = self.paths[idx]

                    if os.path.isdir(path):
                        # If we're selecting and they clicked on the current folder again, select it
                        if self.select_file and path == self.cwd:
                            self.selected_path = path
                            self.dialog.finish()
                            return self.selected_path
                        # Otherwise, descend into it
                        else:
                            self._load_dir(path)
                    else:
                        # It's a file, so select it
                        if self.select_file:
                            self.selected_path = path
                            self.dialog.finish()
                            return self.selected_path
                except (ValueError, IndexError):
                    pass
        return None


class ShortcutManager:
    def __init__(self):
        with tg.Connection() as conn:
            self.conn = conn
            self.activity = tg.Activity(conn)
            self.lock = threading.Lock()
            self.current_tab = 0
            self.selected_index = -1
            self.selected_prefix = -1
            self.selected_template = -1
            self.shortcuts = []
            self.short_buttons = []
            self.prefixes = []
            self.prefix_buttons = []
            self.templates = []
            self.template_buttons = []
            self.running_processes = {} # Track running shortcuts (keyed by shortcut path)
            # Setup controller
            self.controller = view_controller.ViewController()
            # Setup dirs
            self.home = os.getenv('HOME')
            xdg_data = os.getenv('XDG_DATA_HOME', os.path.join(self.home, '.local', 'share'))
            self.applications_dir = os.path.join(xdg_data, 'applications')
            os.makedirs(self.applications_dir, exist_ok=True)

            self.last_manual_switch = 0  # Timestamp of last manual tab switch

            # XDG desktop (fallback ~/Desktop)
            self.desktop_dir = self._get_xdg_user_dir('DESKTOP') or os.path.join(self.home, 'Desktop')
            os.makedirs(self.desktop_dir, exist_ok=True)
            # Wine prefixes
            self.prefixes_file = os.path.join(self.home, '.wine_prefixes.json')
            if not os.path.exists(self.prefixes_file):
                with open(self.prefixes_file, 'w') as f:
                    json.dump([], f)
            self._setup_ui()
            self._event_loop()

    def _get_xdg_user_dir(self, dir_type):
        try:
            return subprocess.check_output(['xdg-user-dir', dir_type]).strip().decode('utf-8')
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None

    def _update_buttons(self):
        is_sc = (self.current_tab == 0)
        is_pf = (self.current_tab == 1)
        is_tm = (self.current_tab == 2)
        has_sc = (self.selected_index >= 0)
        has_pf = (self.selected_prefix >= 0)
        has_tm = (self.selected_template >= 0)

        # “Add” only on Prefixes & Templates
        self.btn_add.setvisibility(
            tg.View.VISIBLE if (is_pf or is_tm) else tg.View.GONE
        )
        # “Run” only on Shortcuts when one is selected
        self.btn_run.setvisibility(
            tg.View.VISIBLE if is_sc and has_sc else tg.View.GONE
        )
        if is_sc and has_sc and self.selected_index < len(self.shortcuts):
            _, selected_path = self.shortcuts[self.selected_index]
            proc = self.running_processes.get(selected_path)
            is_running = proc is not None and proc.poll() is None
            if proc is not None and not is_running:
                del self.running_processes[selected_path]
            if is_running:
                self.btn_run.settext("Stop")
                self.btn_run.setbackgroundcolor(0xFFB71C1C)
                self.btn_run.settextcolor(0xFFFFFFFF)
            else:
                self.btn_run.settext("Run")
                self.btn_run.setbackgroundcolor(0xFF2E7D32)
                self.btn_run.settextcolor(0xFFFFFFFF)
        # “Edit” & “Delete” when something’s selected in the active tab
        show_ed = (is_sc and has_sc) or (is_pf and has_pf) or (is_tm and has_tm)
        self.btn_edit.setvisibility(tg.View.VISIBLE if show_ed else tg.View.GONE)
        self.btn_delete.setvisibility(tg.View.VISIBLE if show_ed else tg.View.GONE)
        # “Kill” on Apps & Wine tabs (not Templates/Help)
        self.btn_kill.setvisibility(tg.View.VISIBLE if (is_sc or is_pf) else tg.View.GONE)

    def _clamp_tab_index(self, tab: int) -> int:
        max_tab = len(getattr(self, "tab_labels", [])) - 1
        if max_tab < 0:
            return 0
        if tab < 0:
            return 0
        if tab > max_tab:
            return max_tab
        return tab


    def _get_shortcuts(self):
        data = self.controller.get_shortcuts_data()
        # Convert dict list to list of tuples (name, path) for existing logic
        return [(item['name'], item['path']) for item in data]

    def _load_prefixes(self):
        return self.controller.get_prefixes_data()

    def _save_prefixes(self, prefixes):
        config.save_prefixes(prefixes)

    def _setup_ui(self):
        a = self.activity

        # Root layout
        root = tg.LinearLayout(a, vertical=True)

        # termuxgui expects ARGB ints (0xAARRGGBB)
        tab_bg_active = 0xFF1E88E5
        tab_bg_inactive = 0xFF333333
        tab_text_active = 0xFFFFFFFF
        tab_text_inactive = 0xFFDDDDDD

        action_bg = 0xFF333333
        action_text = 0xFFFFFFFF
        action_run_bg = 0xFF2E7D32
        action_delete_bg = 0xFFC62828
        action_kill_bg = 0xFFEF6C00

        def make_chip(
            label: str,
            parent,
            *,
            bg: int,
            fg: int,
            text_size: int = 11,
            margin_right: int = 2,
            pad_spaces: int = 1,
            margin_v: int = 0,
        ):
            # Add spaces to simulate padding (termuxgui doesn't expose setpadding).
            pad = " " * max(0, pad_spaces)
            tv = tg.TextView(a, f"{pad}{label}{pad}", parent)
            tv.sendclickevent(True)
            tv.settextsize(text_size)
            tv.setwidth(tg.View.WRAP_CONTENT)
            tv.setheight(tg.View.WRAP_CONTENT)
            tv.setmargin(0)
            if margin_v:
                tv.setmargin(margin_v, "top")
                tv.setmargin(margin_v, "bottom")
            if margin_right:
                tv.setmargin(margin_right, "right")
            tv.setgravity(0, 0)
            tv.setbackgroundcolor(bg)
            tv.settextcolor(fg)
            tv.setlinearlayoutparams(0)
            return tv

        def style_action_button(btn: tg.Button, *, bg: int, fg: int, margin_right: int = 2):
            btn.settextsize(11)
            btn.setwidth(tg.View.WRAP_CONTENT)
            btn.setheight(tg.View.WRAP_CONTENT)
            btn.setmargin(0)
            if margin_right:
                btn.setmargin(margin_right, "right")
            btn.setgravity(1, 1)
            btn.setbackgroundcolor(bg)
            btn.settextcolor(fg)
            btn.setlinearlayoutparams(0)

        def style_add_button(btn: tg.Button):
            btn.settextsize(14)
            btn.setwidth(tg.View.MATCH_PARENT)
            btn.setheight(tg.View.WRAP_CONTENT)
            btn.setmargin(10)
            btn.setgravity(1, 1)
            btn.setbackgroundcolor(0xFF1565C0)
            btn.settextcolor(0xFFFFFFFF)
            btn.setlinearlayoutparams(0)

        # Make available before first _refresh_content()
        self._style_add_button = style_add_button

        # Title
        tv_title = tg.TextView(a, f'{__app_name__} {__version__}', root)
        tv_title.settextsize(20)
        tv_title.setmargin(5)
        tv_title.setwidth(tg.View.MATCH_PARENT)
        tv_title.setheight(tg.View.WRAP_CONTENT)
        tv_title.setlinearlayoutparams(0)

        # Button row
        btn_scroll = tg.HorizontalScrollView(a, root, nobar=True)
        btn_scroll.setmargin(3)
        btn_scroll.setwidth(tg.View.MATCH_PARENT)
        btn_scroll.setheight(tg.View.WRAP_CONTENT)
        btn_scroll.setlinearlayoutparams(0)
        btns = tg.LinearLayout(a, btn_scroll, vertical=False)
        btns.setwidth(tg.View.WRAP_CONTENT)
        btns.setheight(tg.View.WRAP_CONTENT)
        self.btn_add = tg.Button(a, "Add", btns)
        self.btn_add.sendclickevent(True)
        style_action_button(self.btn_add, bg=action_bg, fg=action_text)
        self.btn_run = tg.Button(a, "Run", btns)
        self.btn_run.sendclickevent(True)
        style_action_button(self.btn_run, bg=action_run_bg, fg=action_text)
        self.btn_edit = tg.Button(a, "Edit", btns)
        self.btn_edit.sendclickevent(True)
        style_action_button(self.btn_edit, bg=action_bg, fg=action_text)
        self.btn_delete = tg.Button(a, "Delete", btns)
        self.btn_delete.sendclickevent(True)
        style_action_button(self.btn_delete, bg=action_delete_bg, fg=action_text)
        self.btn_kill = tg.Button(a, "Kill", btns)
        self.btn_kill.sendclickevent(True)
        style_action_button(self.btn_kill, bg=action_kill_bg, fg=action_text, margin_right=0)

        # Tabs (scrollable buttons to keep visible on narrow screens)
        self.tab_labels = ['Apps', 'Wine', 'Tpl', 'Help']
        self.tab_buttons = []
        tab_scroll = tg.HorizontalScrollView(a, root, nobar=True)
        tab_scroll.setmargin(3)
        tab_scroll.setwidth(tg.View.MATCH_PARENT)
        tab_scroll.setheight(tg.View.WRAP_CONTENT)
        tab_scroll.setlinearlayoutparams(0)
        tab_row = tg.LinearLayout(a, tab_scroll, vertical=False)
        tab_row.setwidth(tg.View.WRAP_CONTENT)
        tab_row.setheight(tg.View.WRAP_CONTENT)
        for label in self.tab_labels:
            tv = make_chip(
                label,
                tab_row,
                bg=tab_bg_inactive,
                fg=tab_text_inactive,
                text_size=17,
                margin_right=10,
                pad_spaces=4,
                margin_v=4,
            )
            self.tab_buttons.append(tv)
        self._sync_tab_buttons()

        # Pages (no swipe): stack wrappers and toggle visibility.
        self.page_wrappers = []

        def make_page():
            wrap = tg.NestedScrollView(a, root)
            wrap.setwidth(tg.View.MATCH_PARENT)
            wrap.setheight(0)
            wrap.setlinearlayoutparams(1)
            self.page_wrappers.append(wrap)
            return wrap

        sc_wrap = make_page()
        self.sc_container = tg.LinearLayout(a, sc_wrap)

        pf_wrap = make_page()
        self.pf_container = tg.LinearLayout(a, pf_wrap)

        tm_wrap = make_page()
        self.tm_container = tg.LinearLayout(a, tm_wrap)

        help_wrap = make_page()
        self.help_container = tg.LinearLayout(a, help_wrap, vertical=True)

        # Finally, load the initial data into the real tabs
        self._refresh_content()
        self._show_current_page()
        self._update_buttons()

    def _sync_tab_buttons(self):
        tab_bg_active = 0xFF1E88E5
        tab_bg_inactive = 0xFF333333
        tab_text_active = 0xFFFFFFFF
        tab_text_inactive = 0xFFDDDDDD

        self.current_tab = self._clamp_tab_index(self.current_tab)
        for i, tv in enumerate(self.tab_buttons):
            label = self.tab_labels[i]
            tv.settext(f"    {label}    ")
            if i == self.current_tab:
                tv.setbackgroundcolor(tab_bg_active)
                tv.settextcolor(tab_text_active)
            else:
                tv.setbackgroundcolor(tab_bg_inactive)
                tv.settextcolor(tab_text_inactive)

    def _show_current_page(self):
        self.current_tab = self._clamp_tab_index(self.current_tab)
        for i, wrap in enumerate(getattr(self, "page_wrappers", [])):
            try:
                wrap.setvisibility(tg.View.VISIBLE if i == self.current_tab else tg.View.GONE)
            except Exception:
                pass

    def _recompute_page_width(self):
        return

    def _schedule_recompute_page_width(self):
        return

    def _refresh_content(self):
        # Shortcuts
        self.shortcuts = self._get_shortcuts()
        if self._update_shortcuts_view():
            pass
        else:
            self.short_buttons = []
            self.sc_container.clearchildren()
            for name, path in self.shortcuts:
                label = self._get_shortcut_label(name, path)
                btn = tg.Button(self.activity, label, self.sc_container)
                btn.sendclickevent(True)
                self.short_buttons.append(btn)
            self.selected_index = -1
            
            add_sc = tg.Button(self.activity, '+ Shortcut', self.sc_container)
            add_sc.sendclickevent(True)
            if hasattr(self, "_style_add_button"):
                self._style_add_button(add_sc)
            self.short_buttons.append(add_sc)

        # Prefixes
        self.prefixes = self._load_prefixes()
        self.prefix_buttons = []
        self.pf_container.clearchildren()

        for pre in self.prefixes:
            # pre is now a dict
            name = pre.get('name', 'Unknown')
            path = pre.get('path', '?')
            btn = tg.Button(self.activity, f"{name}", self.pf_container)
            btn.setmargin(10)
            btn.sendclickevent(True)
            self.prefix_buttons.append(btn)
        
        add_pf = tg.Button(self.activity, '+ Prefix', self.pf_container)
        add_pf.sendclickevent(True)
        if hasattr(self, "_style_add_button"):
            self._style_add_button(add_pf)
        self.prefix_buttons.append(add_pf)
        
        # Templates
        self.templates = self.controller.get_templates_data()
        self.template_buttons = []
        self.tm_container.clearchildren()
        for name in self.templates:
            btn = tg.Button(self.activity, name, self.tm_container)
            btn.sendclickevent(True)
            self.template_buttons.append(btn)
        self.selected_template = -1
        add_tm = tg.Button(self.activity, '+ Template', self.tm_container)
        add_tm.sendclickevent(True)
        if hasattr(self, "_style_add_button"):
            self._style_add_button(add_tm)
        self.template_buttons.append(add_tm)

        # Help
        self.help_container.clearchildren()
        
        tv_ver = tg.TextView(self.activity, f"{__app_name__} v{__version__}", self.help_container)
        tv_ver.settextsize(18)
        tv_ver.setmargin(10)
        
        tv_author = tg.TextView(self.activity, "Created by moio9", self.help_container)
        tv_author.setmargin(5)
        
        self.btn_update = tg.Button(self.activity, "Check for Updates", self.help_container)
        self.btn_update.sendclickevent(True)
        
        tv_git = tg.TextView(self.activity, "GitHub: github.com/moio9/barrel", self.help_container)
        tv_git.setmargin(10)

    def _get_shortcut_label(self, name: str, path: str) -> str:
        proc = self.running_processes.get(path)
        if proc is None:
            return name
        if proc.poll() is not None:
            del self.running_processes[path]
            return name
        return f"[STOP] {name}"

    def _update_shortcuts_view(self) -> bool:
        """Update shortcut button labels without creating/destroying views.
        Returns True if updated in-place, False if a rebuild is needed."""
        try:
            expected = len(self.shortcuts) + 1  # + Shortcut
            if not getattr(self, "short_buttons", None) or len(self.short_buttons) != expected:
                return False
            for i, (name, path) in enumerate(self.shortcuts):
                self.short_buttons[i].settext(self._get_shortcut_label(name, path))
            return True
        except Exception:
            return False

    def _start_scroll_watcher(self):
        # Deprecated: do not poll getscrollposition() from a background thread.
        # termuxgui uses a single underlying socket; concurrent reads can crash/hang.
        return

    def _prompt_name(self, text):
        dlg = tg.Activity(self.conn, dialog=True)
        root = tg.LinearLayout(dlg)
        tg.TextView(dlg, text, root).setmargin(5)
        et = tg.EditText(dlg, '', root)
        btns = tg.LinearLayout(dlg, root, False)
        ok = tg.Button(dlg, 'OK', btns)
        cancel = tg.Button(dlg, 'Cancel', btns)
        name = None
        for ev in self.conn.events():
            if ev.type == tg.Event.click and ev.value['id'] == ok:
                name = et.gettext().strip()
                dlg.finish()
                break
            if ev.type == tg.Event.click and ev.value['id'] == cancel:
                dlg.finish()
                break
        return name
                        
    def _get_github_releases(self, owner, repo):
        return updater.get_github_releases(owner, repo)

    def _get_runners(self):
        runners = self.controller.get_available_runners()
        # Convert list of strings to list of tuples (label, cmd)
        return [(r, r) for r in runners]
        
        
    def _extract_exe_icon(self, exe_path, output_path):
        """
        Use wrestool (and optionally ImageMagick's convert) to pull
        the first icon resource (type 14) from a Windows .exe into a PNG.
        """
        try:
            # wrestool -x -t 14 -o <output> <exe>
            subprocess.run(
                ["wrestool", "-x", "-t", "14", "-o", output_path, exe_path],
                check=True
            )
            # optionally resize to 48×48 if imagemagick is installed
            if shutil.which("convert"):
                subprocess.run(
                    ["convert", output_path, "-resize", "48x48", output_path],
                    check=True
                )
            return os.path.exists(output_path)
        except Exception as e:
            print(f"Error extracting icon: {e}")
            return False

        
    def _show_create_prefix_dialog(self):
        # 1) Build the dialog
        dlg = tg.Activity(self.conn, dialog=True)
        root = tg.LinearLayout(dlg)

        # Title
        tv = tg.TextView(dlg, "Create/Add Wine Prefix", root)
        tv.settextsize(18)
        tv.setmargin(5)

        # Name input
        tg.TextView(dlg, "Name (required for new):", root).setmargin(5)
        name_edit = tg.EditText(dlg, "", root)

        # Runner selector
        tg.TextView(dlg, "Runner:", root).setmargin(5)
        runner_spinner = tg.Spinner(dlg, root)
        runners = [label for label, cmd in self._get_runners()]
        runner_spinner.setlist(runners)
        selected_runner = runners[0] if runners else "wine"

        # Architecture selector
        tg.TextView(dlg, "Architecture:", root).setmargin(5)
        arch_spinner = tg.Spinner(dlg, root)
        arches = ["win64", "win32"]
        arch_spinner.setlist(arches)
        selected_arch = arches[0]

        # Buttons row
        btns = tg.LinearLayout(dlg, root, False)
        btn_create = tg.Button(dlg, "Create New", btns)
        btn_browse = tg.Button(dlg, "Browse Existing", btns)
        btn_cancel = tg.Button(dlg, "Cancel", btns)

        # 2) Event loop
        for ev in self.conn.events():
            # keep our selection in sync
            if ev.type == tg.Event.itemselected:
                if ev.value["id"] == runner_spinner:
                    selected_runner = ev.value["selected"]
                elif ev.value["id"] == arch_spinner:
                    selected_arch = ev.value["selected"]

            # handle clicks
            if ev.type == tg.Event.click:
                vid = ev.value["id"]
                name_val = name_edit.gettext().strip()

                if vid == btn_create:
                    if not name_val:
                        self._show_message("Error", "Please enter a name for the new prefix.")
                        continue
                    
                    dlg.finish()

                    # Define standardized path
                    base_dir = Path.home() / ".local/share/barrel/prefixes"
                    base_dir.mkdir(parents=True, exist_ok=True)
                    prefix_path = str(base_dir / name_val)

                    # Initialize
                    runner_cmd = dict(self._get_runners()).get(selected_runner, "wine")
                    env = os.environ.copy()
                    env["WINEPREFIX"] = prefix_path
                    env["WINEARCH"] = selected_arch
                    
                    self._show_message("Info", f"Creating prefix at {prefix_path}...\nThis may take a moment.")

                    try:
                        subprocess.run([runner_cmd, "wineboot"], env=env, check=True)
                    except Exception as e:
                        self._show_message("Error", f"Failed to initialize prefix:\n{e}")
                        return

                    self.prefixes.append({"name": name_val, "path": prefix_path, "runner": selected_runner})
                    self._save_prefixes(self.prefixes)
                    self._refresh_content()
                    return

                elif vid == btn_browse:
                    # ask for a folder
                    fe = FileExplorer(self.conn, select_file=True) # select_file=True often means directory or file depending on impl, assuming directory per original code
                    prefix_path = fe.run()
                    if not prefix_path:
                        continue
                    
                    dlg.finish()

                    if not name_val:
                        name_val = os.path.basename(prefix_path)

                    self.prefixes.append({"name": name_val, "path": prefix_path, "runner": selected_runner})
                    self._save_prefixes(self.prefixes)
                    self._refresh_content()
                    return

                elif vid == btn_cancel:
                    dlg.finish()
                    return
                    return

                elif vid == btn_cancel:
                    dlg.finish()
                    return

                    
    def _show_edit_prefix_dialog(self, prefix_data):
        prefix_path = prefix_data['path']
        prefix_name = prefix_data.get('name', 'Unknown')
        current_runner = prefix_data.get('runner', 'wine')
        
        # 1) Build the dialog
        dlg = tg.Activity(self.conn, dialog=True)
        root = tg.LinearLayout(dlg)
        tv = tg.TextView(dlg, f"Edit Prefix: {prefix_name}\n{prefix_path}", root)
        tv.settextsize(18)
        tv.setmargin(5)
        scroll = tg.NestedScrollView(dlg, root)
        container = tg.LinearLayout(dlg, scroll, vertical=True)

        # Runner selection
        tg.TextView(dlg, "Default Runner:", container).setmargin(5)
        runner_spinner = tg.Spinner(dlg, container)
        runners_list = [label for label, cmd in self._get_runners()]
        runner_spinner.setlist(runners_list)
        
        # Select current runner
        if current_runner in runners_list:
            runner_spinner.selectitem(runners_list.index(current_runner))
        
        # Buttons for actions
        tg.TextView(dlg, "Tools:", container).setmargin(10)
        btn_winecfg = tg.Button(dlg, "Run Winecfg", container)
        btn_winetricks = tg.Button(dlg, "Run Winetricks", container)
        
        tg.TextView(dlg, "Utils:", container).setmargin(10)
        btn_dxvk = tg.Button(dlg, "Install DXVK GPLAsync", container)
        
        # Registry import (if available)
        reg_dir = os.path.join(self.home, 'registry')
        reg_files = glob.glob(os.path.join(reg_dir, '*.reg')) if os.path.exists(reg_dir) else []
        btn_import = None
        reg_spinner = None
        if reg_files:
            tg.TextView(dlg, "Import Registry:", container).setmargin(5)
            reg_spinner = tg.Spinner(dlg, container)
            reg_names = [os.path.basename(f) for f in reg_files]
            reg_spinner.setlist(reg_names)
            btn_import = tg.Button(dlg, "Import Selected", container)

        # Close button
        btn_close = tg.Button(dlg, "Close", container)

        for ev in self.conn.events():
            # Handle Runner Change
            if ev.type == tg.Event.itemselected and ev.value['id'] == runner_spinner:
                new_runner = ev.value['selected']
                if new_runner != current_runner:
                    current_runner = new_runner
                    # Save immediately
                    prefix_data['runner'] = current_runner
                    # Update global list
                    for p in self.prefixes:
                        if p['path'] == prefix_path:
                            p['runner'] = current_runner
                    self._save_prefixes(self.prefixes)
            
            if ev.type == tg.Event.click:
                vid = ev.value['id']
                if vid == btn_winetricks:
                    try:
                        # Winetricks might need WINE env var if the runner is exotic, 
                        # but standard usage expects 'wine' in path.
                        # We try to inject the runner as the wine command.
                        env = os.environ.copy()
                        env['WINEPREFIX'] = prefix_path
                        if "DISPLAY" not in env:
                            env["DISPLAY"] = ":0"
                            try:
                                subprocess.run(
                                    ["am", "start", "-n", "com.termux.x11/com.termux.x11.MainActivity"],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL
                                )
                            except Exception:
                                pass
                        # If the runner is not 'wine', we might need to tell winetricks about it
                        # For now, standard behavior.
                        subprocess.run(['winetricks'], env=env, check=True)
                    except Exception as e:
                        print(f"Winetricks error: {e}")
                        
                elif vid == btn_winecfg:
                    try:
                        env = os.environ.copy()
                        env["WINEPREFIX"] = prefix_path
                        if "DISPLAY" not in env:
                            env["DISPLAY"] = ":0"
                            try:
                                subprocess.run(
                                    ["am", "start", "-n", "com.termux.x11/com.termux.x11.MainActivity"],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL
                                )
                            except Exception:
                                pass
                        subprocess.run([current_runner, "winecfg"], env=env, check=True)
                    except FileNotFoundError:
                        self._show_message("Error", f"Runner '{current_runner}' not found.")
                    except Exception as e:
                        self._show_message("Error", f"Failed: {e}")

                elif vid == btn_dxvk:
                    def show_error_cb(t, m): self._show_message(t, m)
                    def show_info_cb(t, m): self._show_message(t, m)
                    def select_version_cb(opts): return self._prompt_list_choice("Select DXVK Version", opts)
                    
                    installers.install_dxvk_gplasync(show_error_cb, show_info_cb, select_version_cb, prefix_path)

                elif vid == btn_import and btn_import:
                    idx = reg_spinner.getselection()
                    if idx >= 0:
                        reg_file = reg_files[idx]
                        try:
                            env = os.environ.copy()
                            env["WINEPREFIX"] = prefix_path
                            if "DISPLAY" not in env:
                                env["DISPLAY"] = ":0"
                                try:
                                    subprocess.run(
                                        ["am", "start", "-n", "com.termux.x11/com.termux.x11.MainActivity"],
                                        stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL
                                    )
                                except Exception:
                                    pass
                            subprocess.run([current_runner, 'regedit', reg_file], env=env, check=True)
                            self._show_message("Success", f"Imported {os.path.basename(reg_file)}")
                        except Exception as e:
                            self._show_message("Error", str(e))

                elif vid == btn_close:
                    dlg.finish()
                    return
                    
    def _show_message(self, title, message):
        dlg = tg.Activity(self.conn, dialog=True)
        root = tg.LinearLayout(dlg)
        tv = tg.TextView(dlg, title, root)
        tv.settextsize(18)
        tv.setmargin(5)
        tg.TextView(dlg, message, root).setmargin(5)
        btn_ok = tg.Button(dlg, "OK", root)
        for ev in self.conn.events():
            if ev.type == tg.Event.click and ev.value['id'] == btn_ok:
                dlg.finish()
                break
                
    def _show_edit_shortcut_dialog(self, details, path):
        """Shows a dialog to edit a shortcut."""
        dlg = tg.Activity(self.conn, dialog=True)
        root = tg.LinearLayout(dlg)
        scroll = tg.NestedScrollView(dlg, root)
        container = tg.LinearLayout(dlg, scroll, vertical=True)

        # Name field
        tg.TextView(dlg, "Name:", container).setmargin(5)
        name_edit = tg.EditText(dlg, details['name'], container)

        # Template spinner
        tg.TextView(dlg, "Template:", container).setmargin(5)
        template_names = list(self.templates.keys())
        tpl_spinner = tg.Spinner(dlg, container)
        tpl_spinner.setlist(template_names)
        
        selected_tpl_name = details.get('template')
        if selected_tpl_name in template_names:
            # Select current template
            for i, name in enumerate(template_names):
                if name == selected_tpl_name:
                    tpl_spinner.selectitem(i)
                    break
        
        # Terminal radio buttons
        tg.TextView(dlg, "Run in Terminal:", container).setmargin(5)
        rg = tg.RadioGroup(dlg, container)
        rb_yes = tg.RadioButton(dlg, "Yes", rg)
        rb_no  = tg.RadioButton(dlg, "No",  rg)
        if details['terminal']:
            rb_yes.setchecked(True)
        else:
            rb_no.setchecked(True)
        selected_term = details['terminal']

        # Buttons row
        btns = tg.LinearLayout(dlg, container, vertical=False)
        btn_save   = tg.Button(dlg, "Save",   btns)
        btn_cancel = tg.Button(dlg, "Cancel", btns)

        # Event loop for this dialog     
        for ev in self.conn.events():
            if ev.type == tg.Event.itemselected and ev.value['id'] == tpl_spinner:
                selected_tpl_name = ev.value['selected']

            elif ev.type == tg.Event.selected and ev.value['id'] == rg:
                selected_term = (ev.value['selected'] == rb_yes)

            elif ev.type == tg.Event.click:
                vid = ev.value['id']
                if vid == btn_save:
                    new_name = name_edit.gettext().strip() or details['name']
                    
                    # Re-build the exec command
                    python_executable = sys.executable
                    main_script_path = Path(__file__).parent.absolute() / 'app' / 'main.py'
                    
                    cmd_parts = [
                        f'"{python_executable}"',
                        f'"{main_script_path}"',
                        f'--template "{selected_tpl_name}"',
                        f'"{details["executable_path"]}"',
                        '--wait'
                    ]
                    new_exec = " ".join(cmd_parts)

                    new_details = {
                        'name': details['name'],
                        'new_name': new_name,
                        'exec': new_exec,
                        'icon': details['icon'],
                        'terminal': selected_term,
                        'executable_path': details['executable_path'],
                        'desktop_dir': self.desktop_dir,
                        'template': selected_tpl_name
                    }
                    
                    shortcuts.update_shortcut(path, new_details)

                    dlg.finish()
                    self._refresh_content()
                    break

                elif vid == btn_cancel:
                    dlg.finish()
                    break


    def _show_template_dialog(self, template_name=None):
        """Shows a dialog to create or edit a template."""
        from app import actions
        is_edit = template_name is not None
        
        if is_edit:
            t_data = self.templates.get(template_name, {})
        else:
            t_data = self.controller.get_template_form_defaults()

        dlg = tg.Activity(self.conn, dialog=True)
        root = tg.LinearLayout(dlg)
        scroll = tg.NestedScrollView(dlg, root)
        container = tg.LinearLayout(dlg, scroll, vertical=True)
        
        # Dictionary to hold widget references for value retrieval
        self.form_widgets = {}
        # Dictionary to track spinner selection indices
        self.spinner_indices = {}

        # 1. Template Name (Identity)
        tg.TextView(dlg, "Template Name:", container).setmargin(5)
        class _StaticText:
            def __init__(self, text: str):
                self._text = text

            def gettext(self) -> str:
                return self._text

        if is_edit:
            tv_name = tg.TextView(dlg, template_name or "", container)
            tv_name.setmargin(5)
            self.form_widgets["_id"] = _StaticText(template_name or "")
        else:
            name_edit = tg.EditText(dlg, "", container)
            self.form_widgets["_id"] = name_edit

        # 2. Build form from Schema
        schema = self.controller.get_template_ui_schema()
        
        # Helper for Env vars
        env_dict = {k: v for k, v in (e.split('=', 1) for e in t_data.get("env", []) if '=' in e)}
        self.env_special_widgets = {}

        for section in schema:
            # Section Header
            st = tg.TextView(dlg, f"--- {section['section']} ---", container)
            st.settextsize(16)
            st.setmargin(10)
            
            for field in section["fields"]:
                key = field["key"]
                
                # --- Special Case: Env Manager ---
                if field["type"] == "env_manager":
                    # WINEPREFIX
                    tg.TextView(dlg, "WINEPREFIX:", container).setmargin(5)
                    prefix_edit = tg.EditText(dlg, env_dict.get("WINEPREFIX", ""), container)
                    self.env_special_widgets["prefix"] = prefix_edit
                    # DXVK
                    tg.TextView(dlg, "DXVK HUD:", container).setmargin(5)
                    dxvk_spinner = tg.Spinner(dlg, container)
                    dxvk_opts = list(actions.DXVK_MAP.keys())
                    dxvk_spinner.setlist(dxvk_opts)
                    # Set selection
                    cur_dxvk = env_dict.get("DXVK_HUD", "none")
                    dxvk_idx = dxvk_opts.index(cur_dxvk) if cur_dxvk in dxvk_opts else 0
                    dxvk_spinner.selectitem(dxvk_idx)
                    dxvk_spinner.selected_index = dxvk_idx
                    self.env_special_widgets["dxvk"] = (dxvk_spinner, dxvk_opts)

                    # Vulkan
                    tg.TextView(dlg, "Vulkan Driver:", container).setmargin(5)
                    vk_spinner = tg.Spinner(dlg, container)
                    vk_opts = list(actions.VK_MAP.keys())
                    vk_spinner.setlist(vk_opts)
                    cur_vk_val = env_dict.get("VK_ICD_FILENAMES", "")
                    cur_vk = next((k for k, v in actions.VK_MAP.items() if v == cur_vk_val), "None")
                    vk_idx = vk_opts.index(cur_vk) if cur_vk in vk_opts else 0
                    vk_spinner.selectitem(vk_idx)
                    vk_spinner.selected_index = vk_idx
                    self.env_special_widgets["vk"] = (vk_spinner, vk_opts)
                    
                    # FEX
                    tg.TextView(dlg, "Emulator:", container).setmargin(5)
                    fex_spinner = tg.Spinner(dlg, container)
                    fex_opts = list(actions.FEX_MAP.keys())
                    fex_spinner.setlist(fex_opts)
                    cur_fex_val = env_dict.get("HODLL", "")
                    cur_fex = next((k for k, v in actions.FEX_MAP.items() if v == cur_fex_val), "None")
                    fex_idx = fex_opts.index(cur_fex) if cur_fex in fex_opts else 0
                    fex_spinner.selectitem(fex_idx)
                    fex_spinner.selected_index = fex_idx
                    self.env_special_widgets["fex"] = (fex_spinner, fex_opts)

                    # Custom Env
                    tg.TextView(dlg, "Custom Env Vars:", container).setmargin(5)
                    custom_env_list = [e for e in t_data.get("env", []) if not any(e.startswith(p) for p in ["WINEPREFIX=", "DXVK_HUD=", "VK_ICD_FILENAMES=", "HODLL="])]
                    custom_env_edit = tg.EditText(dlg, "\n".join(custom_env_list), container)
                    self.env_special_widgets["custom"] = custom_env_edit
                    
                # --- Standard Fields ---
                else:
                    if field["type"] == "checkbox_mapped":
                        val = str(t_data.get(key, ""))
                        on_val = field.get("on_value", "true")
                        off_val = field.get("off_value", "")
                        
                        cb = tg.Checkbox(dlg, field.get("label", key), container)
                        if val == on_val:
                            cb.setchecked(True)
                        else:
                            cb.setchecked(False)
                            
                        self.form_widgets[key] = (cb, "checkbox_mapped", on_val, off_val)
                        
                    elif field["type"] == "combo":
                        tg.TextView(dlg, field.get("label", key), container).setmargin(5)
                        val = str(t_data.get(key, ""))
                        sp = tg.Spinner(dlg, container)
                        opts = field.get("options", [])
                        sp.setlist(opts)
                        idx = opts.index(val) if val in opts else 0
                        sp.selectitem(idx)
                        sp.selected_index = idx
                        self.form_widgets[key] = (sp, opts)
                    else: # EditText
                        tg.TextView(dlg, field.get("label", key), container).setmargin(5)
                        val = str(t_data.get(key, ""))
                        et = tg.EditText(dlg, val, container)
                        self.form_widgets[key] = et

        btns = tg.LinearLayout(dlg, container, vertical=False)
        btn_save = tg.Button(dlg, "Save", btns)
        btn_cancel = tg.Button(dlg, "Cancel", btns)

        for ev in self.conn.events():
            # Track spinner changes manually by searching for the matching widget
            if ev.type == tg.Event.itemselected:
                event_sp = ev.value['id']
                # Check form widgets
                for key, val in self.form_widgets.items():
                    if isinstance(val, tuple) and len(val) == 2 and isinstance(val[0], tg.Spinner):
                        sp, _ = val
                        if sp == event_sp:
                            sp.selected_index = ev.value['selected']
                # Check env special widgets
                for key, val in self.env_special_widgets.items():
                    if isinstance(val, tuple):
                        sp, _ = val
                        if sp == event_sp:
                            sp.selected_index = ev.value['selected']

            if ev.type == tg.Event.click:
                if ev.value['id'] == btn_save:
                    new_name = self.form_widgets["_id"].gettext().strip()
                    if not new_name:
                        self._show_message("Error", "Template name cannot be empty.")
                        continue
                    
                    # 1. Collect Standard Fields
                    new_data = {}
                    for k, widget_data in self.form_widgets.items():
                        if k == "_id": continue
                        
                        if isinstance(widget_data, tuple):
                            # Handle types
                            if len(widget_data) == 4 and widget_data[1] == "checkbox_mapped":
                                cb, _, on_val, off_val = widget_data
                                new_data[k] = on_val if cb.getchecked() else off_val
                            elif len(widget_data) == 2: # Spinner (sp, opts)
                                spinner, opts = widget_data
                                idx = getattr(spinner, 'selected_index', 0)
                                if 0 <= idx < len(opts):
                                    new_data[k] = opts[idx]
                                else:
                                    new_data[k] = ""
                        else: # EditText
                            new_data[k] = widget_data.gettext().strip()

                    # 2. Collect Environment (Special Logic)
                    prefix = self.env_special_widgets["prefix"].gettext().strip()
                    
                    # Helper for spinners
                    def get_spin_val(key):
                        sp, opts = self.env_special_widgets[key]
                        idx = getattr(sp, 'selected_index', 0)
                        if 0 <= idx < len(opts):
                            return opts[idx]
                        return opts[0]

                    dxvk = get_spin_val("dxvk")
                    vk = get_spin_val("vk")
                    fex = get_spin_val("fex")
                    
                    custom_text = self.env_special_widgets["custom"].gettext()
                    custom_vars = [line.strip() for line in custom_text.split('\n') if line.strip()]

                    final_env = actions.assemble_template_env(prefix, dxvk, vk, fex, custom_vars)
                    new_data["env"] = final_env
                    
                    # Use shared action to save
                    success, message = actions.save_template(new_name, new_data)
                    
                    if not success:
                        self._show_message("Error", message)
                        continue
                    
                    dlg.finish()
                    self._refresh_content()
                    break

                elif ev.value['id'] == btn_cancel:
                    dlg.finish()
                    break

    def _prompt_list_choice(self, title, options):
        """Shows a dialog with a spinner and returns the selected option."""
        if not options:
            return None
            
        dlg = tg.Activity(self.conn, dialog=True)
        root = tg.LinearLayout(dlg)
        tg.TextView(dlg, title, root).setmargin(5)
        spinner = tg.Spinner(dlg, root)
        spinner.setlist(options)
        
        btns = tg.LinearLayout(dlg, root, False)
        ok = tg.Button(dlg, 'OK', btns)
        cancel = tg.Button(dlg, 'Cancel', btns)
        
        selected = options[0]
        for ev_inner in self.conn.events():
            if ev_inner.type == tg.Event.itemselected and ev_inner.value['id'] == spinner:
                selected = ev_inner.value['selected']
            if ev_inner.type == tg.Event.click:
                if ev_inner.value['id'] == ok:
                    dlg.finish()
                    return selected
                elif ev_inner.value['id'] == cancel:
                    dlg.finish()
                    return None
        return None

    def _event_loop(self):
        for ev in self.conn.events():
            if ev.type == tg.Event.destroy:
                sys.exit()

            # Orientation / configuration changes
            # Note: `tg.Event.refresh` can fire during scrolling; avoid mutating layout then.
            if ev.type in (tg.Event.config, tg.Event.resume, tg.Event.start):
                self._sync_tab_buttons()
                self._show_current_page()
                self._update_buttons()
                continue

            if ev.type != tg.Event.click:
                continue

            try:
                vid = ev.value['id']
            except Exception:
                continue

            # Tab switch
            if vid in self.tab_buttons:
                self.last_manual_switch = time.time()
                self.current_tab = self._clamp_tab_index(self.tab_buttons.index(vid))
                self.selected_index = -1
                self.selected_prefix = -1
                self.selected_template = -1
                self._sync_tab_buttons()
                self._show_current_page()
                self._update_buttons()
                continue

            try:
                # === Toolbar “Add” ===
                if vid == self.btn_add:
                    if self.current_tab == 1:  # Prefixes
                        self._show_create_prefix_dialog()
                    elif self.current_tab == 2:  # Templates
                        self._show_template_dialog()
                    continue

                # === Toolbar “Kill Wine” ===
                if vid == self.btn_kill:
                    try:
                        subprocess.run(['wineserver', '-k'], stderr=subprocess.DEVNULL)
                        subprocess.run(['pkill', '-f', 'services.exe'], stderr=subprocess.DEVNULL)
                    except Exception:
                        pass
                    self.running_processes.clear()
                    self._refresh_content()
                    self._show_message("Info", "Wine processes killed.")
                    continue

                # === Shortcuts Tab ===
                if self.current_tab == 0:
                    # “+ Shortcut” button is last in short_buttons
                    if vid == self.short_buttons[-1]:
                        # --- Callback Hell ---
                        def ask_string_cb(title, prompt, initial_value=None):
                            return self._prompt_name(prompt)

                        def ask_file_cb(title, initial_dir=None, initial_file=None, file_types=None):
                            fe = FileExplorer(self.conn, select_file=True, start_dir=initial_dir)
                            return fe.run()

                        def show_warning_cb(title, message):
                            self._show_message(title, message)

                        def show_info_cb(title, message):
                            self._show_message(title, message)

                        def extract_exe_icon_cb(exe_path, output_path):
                            return self._extract_exe_icon(exe_path, output_path)

                        def refresh_shortcuts_cb():
                            self._refresh_content()

                        # Ask user to select a template for the new shortcut
                        template_names = list(self.templates.keys())
                        selected_tpl = self._prompt_list_choice("Choose a Template", template_names)

                        if selected_tpl:
                            shortcuts.create_shortcut_common(
                                preselected_path=None,
                                ask_string_cb=ask_string_cb,
                                ask_file_cb=ask_file_cb,
                                show_warning_cb=show_warning_cb,
                                show_info_cb=show_info_cb,
                                extract_exe_icon_cb=extract_exe_icon_cb,
                                refresh_shortcuts_cb=refresh_shortcuts_cb,
                                HOME=self.home,
                                template_name=selected_tpl
                            )
                        continue

                    # select a shortcut
                    if vid in self.short_buttons:
                        self.selected_index = self.short_buttons.index(vid)
                        self._update_buttons()
                        continue

                    # toolbar actions for shortcuts
                    if self.selected_index >= 0:
                        name, path = self.shortcuts[self.selected_index]

                        if vid == self.btn_run:
                            if path in self.running_processes:
                                # STOP logic
                                proc = self.running_processes[path]
                                if proc.poll() is None:
                                    try:
                                        import signal
                                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                                    except Exception:
                                        proc.kill()
                                del self.running_processes[path]
                                self._update_shortcuts_view()
                                self._update_buttons()
                            else:
                                # RUN logic
                                proc = shortcuts.run_shortcut(path)
                                if proc:
                                    self.running_processes[path] = proc
                                    self._update_shortcuts_view()
                                    self._update_buttons()

                        elif vid == self.btn_edit:
                            details = shortcuts.get_shortcut_details(path)
                            if details:
                                self._show_edit_shortcut_dialog(details, path)
                            else:
                                self._show_message("Error", "Could not read shortcut details.")
                        elif vid == self.btn_delete:
                            os.remove(path)
                            self._refresh_content()
                            continue

                # === Prefixes Tab ===
                elif self.current_tab == 1:
                    if vid in self.prefix_buttons:
                        idx = self.prefix_buttons.index(vid)
                        if idx < len(self.prefixes):
                            self.selected_prefix = idx
                            self._update_buttons()
                        elif idx == len(self.prefixes):  # Add Prefix Button
                            self._show_create_prefix_dialog()
                        continue

                    # toolbar actions for prefixes
                    if self.selected_prefix >= 0:
                        prefix = self.prefixes[self.selected_prefix]
                        if vid == self.btn_edit:
                            self._show_edit_prefix_dialog(prefix)
                        elif vid == self.btn_delete:
                            del self.prefixes[self.selected_prefix]
                            self._save_prefixes(self.prefixes)
                            self._refresh_content()
                        continue

                # === Templates Tab ===
                elif self.current_tab == 2:
                    # Add button is handled by main add button
                    if vid in self.template_buttons:
                        idx = self.template_buttons.index(vid)
                        if idx < len(self.templates):
                            self.selected_template = idx
                            self._update_buttons()
                        elif idx == len(self.templates):  # Add Template Button
                            self._show_template_dialog()
                        continue

                    # toolbar actions for templates
                    if self.selected_template >= 0:
                        tpl_name = list(self.templates.keys())[self.selected_template]
                        if vid == self.btn_edit:
                            self._show_template_dialog(template_name=tpl_name)
                        elif vid == self.btn_delete:
                            templates.delete_template(tpl_name)
                            self._refresh_content()
                        continue

                # === Help Tab ===
                elif self.current_tab == 3:
                    if vid == self.btn_update:
                        self._show_message("Update", "Checking for updates...")
                        avail, msg = updater.check_for_updates()
                        if avail:
                            if self._prompt_list_choice(f"{msg}\nDo you want to update now?", ["Yes", "No"]) == "Yes":
                                succ, u_msg = updater.perform_update()
                                self._show_message("Update Result", u_msg)
                                if succ:
                                    updater.restart_app()
                        else:
                            self._show_message("Update Check", msg)
                    continue

            except Exception:
                err = traceback.format_exc(limit=8)
                print(err, file=sys.stderr)
                try:
                    self._show_message("Error", err)
                except Exception:
                    pass
                continue


if __name__ == '__main__':
    ShortcutManager()
