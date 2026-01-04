#!/usr/bin/python
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import shutil
import subprocess
import json
import sys
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

class ShortcutLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{__app_name__} {__version__}")
        self.root.geometry("800x600")
        
        self.HOME = os.path.expanduser("~")
        self.controller = view_controller.ViewController()
        
        # Track running processes: {filename: Popen_object}
        self.running_processes = {}

        # Theme Setup
        self.style = ttk.Style()
        self.current_theme = config.get_setting("theme", "light")
        self.apply_theme()
        
        self.create_menu()
        self.create_main_frame()
        self.notify_runners()
        self.poll_processes()

    def apply_theme(self):
        theme = self.current_theme
        
        if theme == "dark":
            self.style.theme_use('clam') # 'clam' allows easier color customization than 'vista' or 'aqua'
            
            bg_color = "#2d2d2d"
            fg_color = "#ffffff"
            acc_color = "#4a4a4a"
            hl_color = "#3e3e3e"
            
            self.root.configure(bg=bg_color)
            
            self.style.configure(".", background=bg_color, foreground=fg_color, fieldbackground=acc_color)
            self.style.configure("TFrame", background=bg_color)
            self.style.configure("TLabel", background=bg_color, foreground=fg_color)
            self.style.configure("TButton", background=acc_color, foreground=fg_color, bordercolor=hl_color)
            self.style.map("TButton", background=[("active", hl_color)])
            
            self.style.configure("TEntry", fieldbackground=acc_color, foreground=fg_color)
            self.style.configure("TCombobox", fieldbackground=acc_color, foreground=fg_color, arrowcolor=fg_color)
            
            self.style.configure("TLabelframe", background=bg_color, foreground=fg_color)
            self.style.configure("TLabelframe.Label", background=bg_color, foreground=fg_color)
            
            # Scrollbar (simple dark)
            self.style.configure("Vertical.TScrollbar", troughcolor=bg_color, background=acc_color, arrowcolor=fg_color)
            
        else:
            # Reset to standard
            # 'default' or 'clam' with default colors. 
            # Often 'clam' is nicer than 'default' on Termux X11.
            self.style.theme_use('clam') 
            
            # Reset colors to defaults (hard to "unset", so we set to standard grays)
            default_bg = "#d9d9d9"
            default_fg = "black"
            default_field = "white"
            
            self.root.configure(bg=default_bg)
            self.style.configure(".", background=default_bg, foreground=default_fg, fieldbackground=default_field)
            self.style.configure("TFrame", background=default_bg)
            self.style.configure("TLabel", background=default_bg, foreground=default_fg)
            self.style.configure("TButton", background=default_bg, foreground=default_fg)
            self.style.map("TButton", background=[("active", "#ececec")])
            
            self.style.configure("TEntry", fieldbackground=default_field, foreground="black")
            
            self.style.configure("TLabelframe", background=default_bg, foreground=default_fg)
            self.style.configure("TLabelframe.Label", background=default_bg, foreground=default_fg)

    def toggle_theme(self):
        if self.current_theme == "light":
            self.current_theme = "dark"
        else:
            self.current_theme = "light"
        
        config.set_setting("theme", self.current_theme)
        self.apply_theme()
        # Refresh UI to ensure all widgets redraw with new style
        # (Though configure usually handles it, sometimes forceful redraw helps)
        self.create_main_frame()

    def _setup_scrollable_area(self, parent):
        # Container for canvas + scrollbar
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True)
        
        # Canvas needs to match theme bg
        bg_col = self.style.lookup("TFrame", "background")
        canvas = tk.Canvas(container, bg=bg_col, highlightthickness=0)
        
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        frame_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        # Ensure the inner frame resizes with the canvas
        def _configure_canvas(event):
            canvas.itemconfig(frame_id, width=event.width)
        canvas.bind("<Configure>", _configure_canvas)

        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        def _on_linux_scroll_up(event):
             canvas.yview_scroll(-1, "units")
        def _on_linux_scroll_down(event):
             canvas.yview_scroll(1, "units")
             
        # Bind only when mouse is over the canvas
        def _bind_mouse(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
            canvas.bind_all("<Button-4>", _on_linux_scroll_up)
            canvas.bind_all("<Button-5>", _on_linux_scroll_down)
        def _unbind_mouse(event):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", _bind_mouse)
        canvas.bind("<Leave>", _unbind_mouse)

        return scrollable_frame

    def create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Toggle Dark Mode", command=self.toggle_theme)
        menubar.add_cascade(label="View", menu=view_menu)
        
        menubar.add_command(label="Shortcuts", command=self.list_shortcuts)
        menubar.add_command(label="Templates", command=self.list_templates)
        menubar.add_command(label="Prefixes", command=self.manage_prefixes)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Check for Updates", command=self.check_updates)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

    def check_updates(self):
        avail, msg = updater.check_for_updates()
        if avail:
            if messagebox.askyesno("Update Available", f"{msg}\n\nDo you want to update now?"):
                succ, u_msg = updater.perform_update()
                if succ:
                    messagebox.showinfo("Success", u_msg)
                    updater.restart_app()
                else:
                    messagebox.showerror("Update Failed", u_msg)
        else:
            messagebox.showinfo("Update Check", msg)

    def create_main_frame(self):
        if hasattr(self, 'main_frame'):
            self.main_frame.destroy()
        
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(self.main_frame, text=f"{__app_name__} {__version__}", font=("", 14, "bold")).pack(pady=10)
        
        btn_frame = ttk.Frame(self.main_frame)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="Shortcuts", command=self.list_shortcuts).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Templates", command=self.list_templates).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Wine Prefixes", command=self.manage_prefixes).pack(side=tk.LEFT, padx=5)

    def notify_runners(self):
        self.runners = self._get_runners()
        if not self.runners:
            messagebox.showwarning("Warning", "No installed runners found!")

    def poll_processes(self):
        """Check status of running processes and refresh UI if any stopped."""
        ended = []
        for filename, proc in self.running_processes.items():
            if proc.poll() is not None:
                ended.append(filename)
        
        if ended:
            for f in ended:
                del self.running_processes[f]
            # Only refresh if we are currently looking at the shortcuts list
            # We can check if 'scroll_frame' exists or just blindly refresh if simple
            # Ideally, we should just update the specific buttons, but full refresh is easier for now.
            # To avoid disrupting user navigation, we might need a more targeted update in future.
            if hasattr(self, 'current_view') and self.current_view == 'shortcuts':
                self.list_shortcuts()

        self.root.after(1000, self.poll_processes)

    def clear_main_frame(self):
        for widget in self.main_frame.winfo_children():
            widget.destroy()

    def go_back(self):
        self.create_main_frame()

    def list_shortcuts(self):
        self.clear_main_frame()
        self.current_view = 'shortcuts'
        
        header = ttk.Frame(self.main_frame)
        header.pack(fill=tk.X, pady=5)
        ttk.Label(header, text="Shortcuts", font=("", 12, "bold")).pack(side=tk.LEFT)
        
        # Actions
        ttk.Button(header, text="Add Shortcut", command=self.add_shortcut).pack(side=tk.RIGHT)
        ttk.Button(header, text="Kill Wine", command=self.kill_wine).pack(side=tk.RIGHT, padx=5)
        ttk.Button(header, text="Back", command=self.go_back).pack(side=tk.RIGHT, padx=5)

        # Create scrollable area
        scroll_frame = self._setup_scrollable_area(self.main_frame)

        shortcuts_data = self.controller.get_shortcuts_data()

        if not shortcuts_data:
            ttk.Label(scroll_frame, text="No shortcuts found.").pack(pady=20)
        else:
            for item in shortcuts_data:
                self._create_shortcut_item(scroll_frame, item)

    def _create_shortcut_item(self, parent, item):
        filename = item['filename']
        path = item['path']
        
        frame = ttk.Frame(parent, padding=5, relief="groove", borderwidth=1)
        frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(frame, text=item['name'], font=("", 10, "bold")).pack(side=tk.LEFT, padx=5)
        ttk.Label(frame, text=f"({item.get('template', 'No Template')})").pack(side=tk.LEFT, padx=5)
        
        actions = ttk.Frame(frame)
        actions.pack(side=tk.RIGHT)
        
        # Check if running
        is_running = filename in self.running_processes
        
        if is_running:
            btn = tk.Button(actions, text="Stop", bg="red", fg="white", 
                            command=lambda f=filename: self.toggle_run(f, path))
        else:
            btn = ttk.Button(actions, text="Run", 
                             command=lambda f=filename: self.toggle_run(f, path))
        btn.pack(side=tk.LEFT, padx=2)
        
        ttk.Button(actions, text="Edit", command=lambda f=filename: self.edit_shortcut(f)).pack(side=tk.LEFT, padx=2)
        ttk.Button(actions, text="Delete", command=lambda f=filename: self.delete_shortcut(f)).pack(side=tk.LEFT, padx=2)

    def toggle_run(self, filename, path):
        if filename in self.running_processes:
            # STOP
            if messagebox.askyesno("Stop", f"Force stop {filename}?"):
                proc = self.running_processes[filename]
                try:
                    import signal
                    # Kill the process group to ensure children (the actual game) die too
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except Exception as e:
                    print(f"Error killing process: {e}")
                    # Fallback
                    proc.kill()
                
                del self.running_processes[filename]
                self.list_shortcuts()
        else:
            # RUN
            proc = shortcuts.run_shortcut(path)
            if proc:
                self.running_processes[filename] = proc
                self.list_shortcuts()

    def kill_wine(self):
        if messagebox.askyesno("Confirm Kill", "This will force kill ALL Wine/Hangover processes running on the system.\n\nAre you sure?"):
            success, msg = actions.kill_all_wine_processes()
            messagebox.showinfo("Result", msg)

    def delete_shortcut(self, filename):
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{filename}'?"):
            shortcuts.delete_shortcut(filename)
            self.list_shortcuts()

    def list_templates(self):
        self.clear_main_frame()
        self.templates = self.controller.get_templates_data()

        header = ttk.Frame(self.main_frame)
        header.pack(fill=tk.X, pady=5)
        ttk.Label(header, text="Templates", font=("", 12, "bold")).pack(side=tk.LEFT)
        ttk.Button(header, text="Add Template", command=self.add_template).pack(side=tk.RIGHT)
        ttk.Button(header, text="Back", command=self.go_back).pack(side=tk.RIGHT, padx=5)

        # Create scrollable area
        scroll_frame = self._setup_scrollable_area(self.main_frame)

        for name, data in self.templates.items():
            frame = ttk.Frame(scroll_frame, padding=5, relief="groove", borderwidth=1)
            frame.pack(fill=tk.X, pady=5)
            ttk.Label(frame, text=name, font=("", 10, "bold")).pack(anchor="w")
            ttk.Label(frame, text=data.get('description', ''), justify=tk.LEFT).pack(anchor="w")
            
            actions = ttk.Frame(frame)
            actions.pack(side=tk.RIGHT)
            ttk.Button(actions, text="Edit", command=lambda n=name: self.edit_template(n)).pack(side=tk.LEFT)
            ttk.Button(actions, text="Delete", command=lambda n=name: self.delete_template(n)).pack(side=tk.LEFT)

    def add_template(self):
        self._show_template_dialog()

    def edit_template(self, name):
        self._show_template_dialog(template_name=name)

    def delete_template(self, name):
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete the template '{name}'?"):
            templates.delete_template(name)
            self.list_templates()

    def _show_template_dialog(self, template_name=None):
        from app import actions # Local import to get updated maps

        is_edit = template_name is not None
        if is_edit:
            t_data = self.templates.get(template_name, {})
        else:
            # Set default values for new templates
            t_data = {
                "runner": "hangover-wine",
                "env": [
                    f"WINEPREFIX={Path.home() / '.wine'}",
                    f"VK_ICD_FILENAMES={actions.VK_MAP['Freedreno']}"
                ],
                "description": "Default settings for Hangover+Freedreno", "post_exec": ""
            }

    def _show_template_dialog(self, template_name=None):
        from app import actions # Local import to get updated maps

        is_edit = template_name is not None
        if is_edit:
            t_data = self.templates.get(template_name, {})
        else:
            # Set default values for new templates
            t_data = {
                "runner": "hangover-wine",
                "env": [
                    f"WINEPREFIX={Path.home() / '.wine'}",
                    f"VK_ICD_FILENAMES={actions.VK_MAP['Freedreno']}"
                ],
                "description": "Default settings for Hangover+Freedreno", "post_exec": ""
            }

    def _show_template_dialog(self, template_name=None):
        from app import actions 

        is_edit = template_name is not None
        if is_edit:
            t_data = self.templates.get(template_name, {})
        else:
            t_data = self.controller.get_template_form_defaults()

        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Template" if is_edit else "Create Template")
        dialog.geometry("600x850")
        
        # Create scrollable area for the form
        container = self._setup_scrollable_area(dialog)
        
        # Dictionary to hold our Tkinter variables
        self.form_vars = {}
        
        # 1. Template Name is special (ID)
        name_frame = ttk.LabelFrame(container, text="Identity", padding=10)
        name_frame.pack(fill=tk.X, pady=5, padx=5)
        ttk.Label(name_frame, text="Template Name:").pack(anchor="w")
        name_var = tk.StringVar(value=template_name or "")
        name_entry = ttk.Entry(name_frame, textvariable=name_var, state='disabled' if is_edit else 'normal')
        name_entry.pack(fill=tk.X)
        self.form_vars["_id"] = name_var # Internal key for the name

        # 2. Build form from Schema
        schema = self.controller.get_template_ui_schema()
        
        # Helper for Env vars (needed for the special env_manager block)
        env_dict = {k: v for k, v in (e.split('=', 1) for e in t_data.get("env", []) if '=' in e)}
        # Variables specifically for the Env Manager part
        self.env_special_vars = {} 

        for section in schema:
            frame = ttk.LabelFrame(container, text=section["section"], padding=10)
            frame.pack(fill=tk.X, pady=5, padx=5)
            
            for field in section["fields"]:
                key = field["key"]
                
                # --- Special Case: Environment Manager ---
                if field["type"] == "env_manager":
                    # Re-implementing the complex env logic inside the loop
                    # WINEPREFIX
                    ttk.Label(frame, text="WINEPREFIX:").grid(row=0, column=0, sticky="w", pady=2)
                    prefix_var = tk.StringVar(value=env_dict.get("WINEPREFIX", ""))
                    
                    # Load known prefixes for suggestions
                    known_prefixes = [p.get('path') for p in config.load_prefixes()]
                    
                    ttk.Combobox(frame, textvariable=prefix_var, values=known_prefixes).grid(row=0, column=1, sticky="ew", padx=5)
                    
                    def select_prefix(v=prefix_var):
                        path = filedialog.askdirectory(title="Select WINEPREFIX Folder")
                        if path: v.set(path)
                    ttk.Button(frame, text="Browse...", command=select_prefix).grid(row=0, column=2, padx=5)
                    self.env_special_vars["prefix"] = prefix_var

                    # DXVK_HUD
                    ttk.Label(frame, text="DXVK HUD:").grid(row=1, column=0, sticky="w", pady=2)
                    dxvk_var = tk.StringVar(value=env_dict.get("DXVK_HUD", "none"))
                    ttk.Combobox(frame, textvariable=dxvk_var, values=list(actions.DXVK_MAP.keys()), state="readonly").grid(row=1, column=1, sticky="ew", padx=5)
                    self.env_special_vars["dxvk"] = dxvk_var

                    # Vulkan ICD
                    ttk.Label(frame, text="Vulkan Driver:").grid(row=2, column=0, sticky="w", pady=2)
                    current_vk = env_dict.get("VK_ICD_FILENAMES", "")
                    vk_alias = next((k for k, v in actions.VK_MAP.items() if v == current_vk), "None")
                    vk_var = tk.StringVar(value=vk_alias)
                    ttk.Combobox(frame, textvariable=vk_var, values=list(actions.VK_MAP.keys()), state="readonly").grid(row=2, column=1, sticky="ew", padx=5)
                    self.env_special_vars["vk"] = vk_var

                    # FEX/EMU
                    ttk.Label(frame, text="Emulator:").grid(row=3, column=0, sticky="w", pady=2)
                    current_fex = env_dict.get("HODLL", "")
                    fex_alias = next((k for k, v in actions.FEX_MAP.items() if v == current_fex), "None")
                    fex_var = tk.StringVar(value=fex_alias)
                    ttk.Combobox(frame, textvariable=fex_var, values=list(actions.FEX_MAP.keys()), state="readonly").grid(row=3, column=1, sticky="ew", padx=5)
                    self.env_special_vars["fex"] = fex_var
                    
                    frame.columnconfigure(1, weight=1)

                    # Custom Env Vars Text Area
                    ttk.Label(frame, text="Custom Environment Variables:").grid(row=4, column=0, sticky="nw", pady=5)
                    self.custom_env_text = tk.Text(frame, height=4)
                    self.custom_env_text.grid(row=5, column=0, columnspan=3, sticky="ew")
                    custom_env_list = [e for e in t_data.get("env", []) if not any(e.startswith(p) for p in ["WINEPREFIX=", "DXVK_HUD=", "VK_ICD_FILENAMES=", "HODLL="])]
                    self.custom_env_text.insert("1.0", "\n".join(custom_env_list))
                    
                # --- Standard Fields ---
                else:
                    if field["type"] == "checkbox_mapped":
                        # Checkbox that maps to specific string values
                        current_val = str(t_data.get(key, ""))
                        on_val = field.get("on_value", "true")
                        off_val = field.get("off_value", "")
                        
                        is_checked = (current_val == on_val)
                        var = tk.BooleanVar(value=is_checked)
                        
                        # Store tuple: (variable, type, on_val, off_val) to handle saving logic
                        self.form_vars[key] = (var, "checkbox_mapped", on_val, off_val)
                        
                        ttk.Checkbutton(frame, text=field.get("label", key), variable=var).pack(anchor="w")
                        
                    elif field["type"] == "combo":
                        ttk.Label(frame, text=field.get("label", key)).pack(anchor="w")
                        val = t_data.get(key, "")
                        var = tk.StringVar(value=str(val))
                        self.form_vars[key] = var
                        ttk.Combobox(frame, textvariable=var, values=field.get("options", []), state="readonly").pack(fill=tk.X)
                    
                    else: # text
                        ttk.Label(frame, text=field.get("label", key)).pack(anchor="w")
                        val = t_data.get(key, "")
                        var = tk.StringVar(value=str(val))
                        self.form_vars[key] = var
                        ttk.Entry(frame, textvariable=var).pack(fill=tk.X)

        # --- Save / Cancel ---
        def save_changes():
            new_name = self.form_vars["_id"].get().strip()
            if not new_name:
                messagebox.showerror("Error", "Template name cannot be empty.", parent=dialog)
                return
            
            # 1. Collect Standard Fields
            data_to_save = {}
            for k, val_data in self.form_vars.items():
                if k == "_id": continue
                
                # Handle our custom types in form_vars
                if isinstance(val_data, tuple) and len(val_data) == 4 and val_data[1] == "checkbox_mapped":
                    var, _, on_val, off_val = val_data
                    data_to_save[k] = on_val if var.get() else off_val
                elif isinstance(val_data, tk.Variable):
                    data_to_save[k] = val_data.get().strip()
                else:
                    # Fallback for simple vars if any left
                    data_to_save[k] = val_data.get().strip()

            # 2. Collect Environment (Special Logic)
            prefix = self.env_special_vars["prefix"].get().strip()
            dxvk = self.env_special_vars["dxvk"].get()
            vk = self.env_special_vars["vk"].get()
            fex = self.env_special_vars["fex"].get()
            custom_vars = [line.strip() for line in self.custom_env_text.get("1.0", tk.END).split('\n') if line.strip()]
            
            final_env = actions.assemble_template_env(prefix, dxvk, vk, fex, custom_vars)
            data_to_save["env"] = final_env
            
            success, message = actions.save_template(new_name, data_to_save)

            if success:
                messagebox.showinfo("Success", message, parent=dialog)
                dialog.destroy()
                self.list_templates()
            else:
                messagebox.showerror("Error", message, parent=dialog)

        btn_frame = ttk.Frame(container)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Save", command=save_changes).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def edit_shortcut(self, filename):
        path = Path(os.getenv('XDG_DATA_HOME', Path.home()/'.local'/'share')) / 'applications' / 'shortcuts' / filename
        details = shortcuts.get_shortcut_details(str(path))
        
        if not details:
            messagebox.showerror("Error", "Could not read shortcut details.")
            return
        
        self.templates = templates.load_templates()
        template_names = list(self.templates.keys())

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit {details['name']}")
        
        container = ttk.Frame(dialog, padding=10)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(container, text="Name:").pack()
        name_var = tk.StringVar(value=details['name'])
        name_entry = ttk.Entry(container, textvariable=name_var)
        name_entry.pack(fill="x")

        ttk.Label(container, text="Template:").pack()
        template_var = tk.StringVar()
        template_combo = ttk.Combobox(container, textvariable=template_var, values=template_names, state="readonly")
        if details.get('template') in template_names:
            template_var.set(details['template'])
        elif template_names:
            template_var.set(template_names[0])
        template_combo.pack(fill="x")

        def save_changes():
            new_name = name_var.get().strip() or details['name']
            tpl_name = template_var.get()

            python_executable = sys.executable
            main_script_path = Path(__file__).parent.absolute() / 'app' / 'main.py'
            new_exec = f'"{python_executable}" "{main_script_path}" --template "{tpl_name}" "{details["executable_path"]}" --wait'

            new_details = {
                'name': details['name'], 'new_name': new_name, 'exec': new_exec,
                'icon': details['icon'], 'terminal': details['terminal'],
                'executable_path': details['executable_path'],
                'desktop_dir': str(Path.home() / "Desktop"),
                'template': tpl_name
            }

            shortcuts.update_shortcut(str(path), new_details)
            dialog.destroy()
            self.list_shortcuts()

        btn_frame = ttk.Frame(container)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Save", command=save_changes).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT)

    def add_shortcut(self):
        self.templates = templates.load_templates()
        template_names = list(self.templates.keys())
        if not template_names:
            messagebox.showerror("Error", "No templates found. Please create a template first.")
            return

        tpl_dialog = tk.Toplevel(self.root)
        tpl_dialog.title("Choose Template")
        tpl_var = tk.StringVar()
        ttk.Label(tpl_dialog, text="Select a template:").pack(padx=10, pady=10)
        combo = ttk.Combobox(tpl_dialog, textvariable=tpl_var, values=template_names, state="readonly")
        if template_names:
            combo.current(0)
        combo.pack(padx=10, pady=5)
        
        chosen_tpl = None
        def on_ok():
            nonlocal chosen_tpl
            chosen_tpl = tpl_var.get()
            tpl_dialog.destroy()
        
        ttk.Button(tpl_dialog, text="OK", command=on_ok).pack(pady=10)
        self.root.wait_window(tpl_dialog)

        if not chosen_tpl:
            return

        shortcuts.create_shortcut_common(
            preselected_path=None,
            ask_string_cb=lambda t,p,i=None: simpledialog.askstring(t,p,initialvalue=i),
            ask_file_cb=lambda t: filedialog.askopenfilename(title=t),
            show_warning_cb=messagebox.showwarning,
            show_info_cb=messagebox.showinfo,
            extract_exe_icon_cb=lambda e,o: True, # Placeholder
            refresh_shortcuts_cb=self.list_shortcuts,
            HOME=self.HOME,
            template_name=chosen_tpl
        )

    def manage_prefixes(self):
        self.clear_main_frame()
        header = ttk.Frame(self.main_frame)
        header.pack(fill=tk.X, pady=5)
        ttk.Label(header, text="Manage Wine Prefixes", font=("", 12, "bold")).pack(side=tk.LEFT)
        ttk.Button(header, text="Create New Prefix", command=self.create_prefix).pack(side=tk.RIGHT)
        ttk.Button(header, text="Back", command=self.go_back).pack(side=tk.RIGHT, padx=5)

        # Create scrollable area
        scroll_frame = self._setup_scrollable_area(self.main_frame)

        prefixes = self.controller.get_prefixes_data()
        if not prefixes:
            ttk.Label(scroll_frame, text="No prefixes configured.").pack(pady=20)
        else:
            for p in prefixes:
                self._create_prefix_item(scroll_frame, p)

    def _create_prefix_item(self, parent, item):
        name = item.get('name', 'Unknown')
        path = item.get('path', '?')
        
        frame = ttk.Frame(parent, padding=5, relief="groove", borderwidth=1)
        frame.pack(fill=tk.X, pady=5, padx=5)
        ttk.Label(frame, text=f"{name} ({path})").pack(side=tk.LEFT, padx=5)
        
        actions = ttk.Frame(frame)
        actions.pack(side=tk.RIGHT)
        ttk.Button(actions, text="Edit", command=lambda p=item: self.edit_prefix(p)).pack(side=tk.LEFT, padx=2)
        ttk.Button(actions, text="Delete", command=lambda p=item: self.delete_prefix(p)).pack(side=tk.LEFT, padx=2)

    def delete_prefix(self, prefix_data):
        name = prefix_data.get('name', '?')
        path = prefix_data.get('path', '?')
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to remove the prefix '{name}' from the list? This will not delete the folder."):
            prefixes = self.load_prefixes()
            # Remove by path match
            prefixes = [p for p in prefixes if p.get('path') != path]
            self.save_prefixes(prefixes)
            self.manage_prefixes()

    def create_prefix(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Create/Add Wine Prefix")
        dialog.geometry("400x350")
        
        container = ttk.Frame(dialog, padding=10)
        container.pack(fill=tk.BOTH, expand=True)

        # Name
        ttk.Label(container, text="Name:").pack(anchor="w")
        name_var = tk.StringVar()
        ttk.Entry(container, textvariable=name_var).pack(fill=tk.X, pady=(0, 10))

        # Runner
        ttk.Label(container, text="Runner:").pack(anchor="w")
        runner_var = tk.StringVar(value="wine")
        # Attempt to get runners list if available, or just a text entry
        runners = self._get_runners()
        if runners:
             runner_combo = ttk.Combobox(container, textvariable=runner_var, values=runners)
             runner_combo.pack(fill=tk.X, pady=(0, 10))
             if runners: runner_combo.current(0)
        else:
             ttk.Entry(container, textvariable=runner_var).pack(fill=tk.X, pady=(0, 10))

        # Architecture
        ttk.Label(container, text="Architecture:").pack(anchor="w")
        arch_var = tk.StringVar(value="win64")
        ttk.Combobox(container, textvariable=arch_var, values=["win64", "win32"], state="readonly").pack(fill=tk.X, pady=(0, 10))

        def do_create():
            name = name_var.get().strip()
            if not name:
                messagebox.showerror("Error", "Name is required for new prefix.")
                return

            base_dir = Path.home() / ".local/share/barrel/prefixes"
            base_dir.mkdir(parents=True, exist_ok=True)
            prefix_path = str(base_dir / name)
            
            _finalize(name, prefix_path, True)

        def do_browse():
            path = filedialog.askdirectory(title="Choose prefix folder")
            if not path: return
            
            name = name_var.get().strip()
            if not name:
                name = os.path.basename(path)
            
            _finalize(name, path, False) # False = don't force create, just init if needed? Or just add.
            
        def _finalize(name, path, create_mode):
            runner = runner_var.get()
            arch = arch_var.get()
            
            try:
                env = os.environ.copy()
                env["WINEPREFIX"] = path
                env["WINEARCH"] = arch
                
                # If create mode, run wineboot. If browse, maybe user wants to init it too? 
                # Let's assume wineboot is safe to run on existing prefix (it updates it).
                subprocess.run([runner, "wineboot"], env=env, check=True)
                
                prefixes = self.load_prefixes()
                # Check for duplicate paths or names? For now just append.
                # Remove if exists to update
                prefixes = [p for p in prefixes if p.get('path') != path and p.get('name') != name]
                
                prefixes.append({"name": name, "path": path, "runner": runner})
                self.save_prefixes(prefixes)
                
                messagebox.showinfo("Success", f"Prefix '{name}' ready!")
                dialog.destroy()
                self.manage_prefixes()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to setup prefix: {e}")

        btn_frame = ttk.Frame(container)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Create New (Auto)", command=do_create).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Add Existing (Browse)", command=do_browse).pack(side=tk.LEFT, padx=5)


    def edit_prefix(self, prefix_data):
        prefix_path = prefix_data['path']
        prefix_name = prefix_data.get('name', 'Unknown')
        current_runner = prefix_data.get('runner', 'wine')

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit Prefix: {prefix_name}")
        dialog.geometry("400x350")

        container = ttk.Frame(dialog, padding=10)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(container, text=f"{prefix_name}\n{prefix_path}", wraplength=380).pack(pady=5)
        
        # Runner Selector
        ttk.Label(container, text="Default Runner:").pack(anchor="w", pady=(10,0))
        runner_var = tk.StringVar(value=current_runner)
        runners = self._get_runners()
        if not runners: runners = ["wine"]
        
        runner_combo = ttk.Combobox(container, textvariable=runner_var, values=runners, state="readonly")
        runner_combo.pack(fill=tk.X, pady=5)
        
        def on_runner_change(event):
            new_r = runner_var.get()
            # Update data
            prefix_data['runner'] = new_r
            # Update storage
            prefixes = self.load_prefixes()
            for p in prefixes:
                if p['path'] == prefix_path:
                    p['runner'] = new_r
            self.save_prefixes(prefixes)
            
        runner_combo.bind("<<ComboboxSelected>>", on_runner_change)

        ttk.Button(container, text="Run Winetricks", command=lambda: self.run_winetricks(prefix_path, runner_var.get())).pack(fill=tk.X, pady=5)
        ttk.Button(container, text="Run Winecfg", command=lambda: self.run_winecfg(prefix_path, runner_var.get())).pack(fill=tk.X, pady=5)
        ttk.Button(container, text="Install DXVK (GPLAsync)", command=lambda: self.install_dxvk(prefix_path)).pack(fill=tk.X, pady=5)
        ttk.Button(container, text="Close", command=dialog.destroy).pack(pady=10)

    def run_winetricks(self, prefix_path, runner="wine"):
        try:
            env = os.environ.copy()
            env["WINEPREFIX"] = prefix_path
            # Optional: if runner is special, we might want to set WINE env var
            # env["WINE"] = runner 
            subprocess.Popen(["winetricks"], env=env)
        except FileNotFoundError:
            messagebox.showerror("Error", "Winetricks is not installed or not in your PATH.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to run Winetricks: {e}")

    def run_winecfg(self, prefix_path, runner="wine"):
        try:
            env = os.environ.copy()
            env["WINEPREFIX"] = prefix_path
            subprocess.Popen([runner, "winecfg"], env=env)
        except FileNotFoundError:
            messagebox.showerror("Error", f"Runner '{runner}' not found.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to run Winecfg: {e}")

    def install_dxvk(self, prefix_path):
        def show_error(t, m): messagebox.showerror(t, m)
        def show_info(t, m): messagebox.showinfo(t, m)
        
        def select_version_cb(options):
            if not options:
                show_error("Error", "No DXVK versions found.")
                return None

            dialog = tk.Toplevel(self.root)
            dialog.title("Select DXVK Version")
            
            container = ttk.Frame(dialog, padding=10)
            container.pack(fill=tk.BOTH, expand=True)

            ttk.Label(container, text="Please select a DXVK version to install:").pack(pady=5)
            
            version_var = tk.StringVar(value=options[0])
            combo = ttk.Combobox(container, textvariable=version_var, values=options, state="readonly")
            combo.pack(fill=tk.X, pady=5)
            
            chosen_version = None
            def on_ok():
                nonlocal chosen_version
                chosen_version = version_var.get()
                dialog.destroy()

            ttk.Button(container, text="Install", command=on_ok).pack(pady=10)
            self.root.wait_window(dialog)
            return chosen_version

        installers.install_dxvk_gplasync(show_error, show_info, select_version_cb, prefix_path)

    def load_prefixes(self):
        return config.load_prefixes()

    def save_prefixes(self, prefixes):
        config.save_prefixes(prefixes)


    def _get_runners(self):
        """Detects available runners from a predefined list."""
        return self.controller.get_available_runners()

    def show_about(self):
        messagebox.showinfo("About", f"{__app_name__} {__version__}\n\nA simple shortcut launcher.")

if __name__ == "__main__":
	try:
		root = tk.Tk()
		app = ShortcutLauncher(root)
		print("Starting mainloop...")
		root.mainloop()
		print("Mainloop finished.")
	except Exception as e:
		print(f"An error occurred during execution: {e}")
