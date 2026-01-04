from . import templates

VK_MAP = {
    "None": "",
    "Wrapper": "$PREFIX/share/vulkan/icd.d/wrapper_icd.aarch64.json",
    "Freedreno": "$PREFIX/share/vulkan/icd.d/freedreno_icd.aarch64.json"
}
FEX_MAP = {
    "BOX64": "",
    "FEX": "libwow64fex.dll"
}
DXVK_MAP = {
    "none": "",
    "1": "1",
    "full": "full",
    "devinfo,fps": "devinfo,fps"
}

def assemble_template_env(prefix, dxvk_hud, vk_icd_alias, fex_alias, custom_vars):
    """Assembles the final list of environment variables from various sources."""
    final_env = []
    if prefix:
        final_env.append(f"WINEPREFIX={prefix}")
    if dxvk_hud and dxvk_hud != "none":
        final_env.append(f"DXVK_HUD={dxvk_hud}")
    
    vk_val = VK_MAP.get(vk_icd_alias)
    if vk_val:
        final_env.append(f"VK_ICD_FILENAMES={vk_val}")
        
    fex_val = FEX_MAP.get(fex_alias)
    if fex_val:
        final_env.append(f"HODLL={fex_val}")
        
    final_env.extend(custom_vars)
    return sorted(list(set(final_env)))

def save_template(template_name, data):
    """
    Assembles and saves a template profile.
    
    Args:
        template_name (str): The name of the template.
        data (dict): A dictionary containing template fields (description, runner, env, post_exec, etc.)
    """
    if not template_name:
        return False, "Template name cannot be empty."

    all_templates = templates.load_templates()
    
    # Ensure mandatory fields exist or use defaults if strict schema is needed, 
    # but here we trust the UI to pass what's needed.
    # We can explicitly ensure 'env' is a list if present.
    if 'env' in data and not isinstance(data['env'], list):
         return False, "Environment variables must be a list."

    all_templates[template_name] = data
    
    if templates.save_templates(all_templates):
        return True, "Template saved successfully!"
    else:
        return False, "Failed to save templates file."

def kill_all_wine_processes():
    """
    Forcefully kills all known Wine, Hangover, and emulation processes.
    """
    import subprocess
    
    # List of process names/patterns to kill
    targets = [
        "services.exe",
        "wineserver",
        "winedevice.exe",
        "explorer.exe",
        "rpcss.exe",
        "plugplay.exe",
        "wineboot",
        "wine64",
        "wine",
        "hangover",
        "libfex",
        "box64"
    ]
    
    count = 0
    for target in targets:
        try:
            # pkill -9 -f matches the full command line and force kills
            subprocess.run(f"pkill -9 -f {target}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            count += 1
        except Exception:
            pass
            
    return True, "Sent kill signals to Wine processes."

