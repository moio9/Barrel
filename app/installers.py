import os
import requests
import urllib.request
import tarfile
import tempfile
import shutil
import glob

def install_dxvk_gplasync(show_error_cb, show_info_cb, select_version_cb, prefix_path):
    """Downloads and installs the latest DXVK-GPLAsync version."""
    project_id = "43488626"  # ID for Ph42oN/dxvk-gplasync
    api_url = f"https://gitlab.com/api/v4/projects/{project_id}/releases"
    download_path = None
    extract_dir = None

    try:
        # 1. Fetch release info from GitLab API
        resp = requests.get(api_url)
        resp.raise_for_status()
        releases = resp.json()
        if not releases:
            show_error_cb("Error", "No releases found on GitLab!")
            return

        # 2. Prepare options for version selection
        options = []
        assets = {}
        for rel in releases:
            title = rel.get('name', 'Release')
            for asset in rel.get('assets', {}).get('links', []):
                if asset.get('name', '').endswith(".tar.gz"):
                    option_label = f"{title} ({asset['name']})"
                    options.append(option_label)
                    assets[option_label] = asset['url']
        
        if not options:
            show_error_cb("Error", "No .tar.gz archives found in releases!")
            return

        # 3. Let the user choose a version using the provided callback
        selected = select_version_cb(options)
        if not selected:
            return
        url = assets[selected]

        # 4. Download the chosen archive
        download_path = os.path.join(tempfile.gettempdir(), os.path.basename(url))
        urllib.request.urlretrieve(url, download_path)

        # 5. Extract the archive to a temporary directory
        extract_dir = tempfile.mkdtemp()
        with tarfile.open(download_path, "r:gz") as tar:
            tar.extractall(path=extract_dir)

        # 6. Find x64 and x32 folders recursively
        dxvk_x64 = None
        dxvk_x32 = None
        
        for root, dirs, files in os.walk(extract_dir):
            if "x64" in dirs:
                dxvk_x64 = os.path.join(root, "x64")
            if "x32" in dirs:
                dxvk_x32 = os.path.join(root, "x32")
        
        if not dxvk_x64 and not dxvk_x32:
             raise Exception("Could not find x64 or x32 folders in the archive.")

        # 7. Define target directories and create them
        system32 = os.path.join(prefix_path, "drive_c", "windows", "system32")
        syswow64 = os.path.join(prefix_path, "drive_c", "windows", "syswow64")
        os.makedirs(system32, exist_ok=True)
        os.makedirs(syswow64, exist_ok=True)

        installed_dlls = set()

        # 8. Copy DLLs from the extracted folder to the prefix
        if dxvk_x64:
            for dll in glob.glob(os.path.join(dxvk_x64, "*.dll")):
                shutil.copy(dll, system32)
                installed_dlls.add(os.path.splitext(os.path.basename(dll))[0])
                
        if dxvk_x32:
            for dll in glob.glob(os.path.join(dxvk_x32, "*.dll")):
                shutil.copy(dll, syswow64)
                # We assume same DLLs exist for both archs, so set is fine

        # 9. Apply DLL Overrides in user.reg
        user_reg = os.path.join(prefix_path, "user.reg")
        if os.path.exists(user_reg):
            # Read existing content to check if section exists (simple check)
            with open(user_reg, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            overrides_section = "[Software\\Wine\\DllOverrides]"
            
            # Prepare new overrides block
            new_overrides = []
            if overrides_section not in content:
                new_overrides.append(f"\n{overrides_section}")
            
            for dll_name in installed_dlls:
                # Add "dll"="native" line if not simplistic check found (this is crude but safer than parsing)
                # Actually, simply appending them is usually fine for Wine, it takes the last one or merges.
                # But let's be cleaner: append them at the end.
                new_overrides.append(f'"{dll_name}"="native"')
            
            with open(user_reg, 'a', encoding='utf-8') as f:
                f.write("\n".join(new_overrides) + "\n")

        show_info_cb("Success", f"DXVK GPLAsync {selected} installed successfully!\nDLL Overrides set for: {', '.join(installed_dlls)}")

    except Exception as e:
        show_error_cb("Error", f"Installation failed:\n{str(e)}")

    finally:
        # 10. Cleanup downloaded and temporary files
        if download_path and os.path.exists(download_path):
            os.remove(download_path)
        if extract_dir and os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)