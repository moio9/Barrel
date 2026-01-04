import subprocess
import sys
import os
import requests
import zipfile
import io
import shutil
import tempfile
from app import __version__

# Ensure we operate on the directory where the app is installed
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GITHUB_REPO = "moio9/barrel"

def is_git_repo():
    """Checks if the app directory is a git repository."""
    try:
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL, 
            cwd=REPO_DIR,
            check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def get_latest_tag():
    """Fetches the latest tag from GitHub."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/tags"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        tags = r.json()
        if not tags:
            return None, None
        # Assuming the first one is the latest (GitHub API default sort)
        latest = tags[0]
        return latest.get('name'), latest.get('zipball_url')
    except Exception as e:
        print(f"Error fetching tags: {e}")
        return None, None

def compare_versions(new_ver, current_ver):
    """
    Returns True if new_ver > current_ver.
    Handles 'v' prefix.
    """
    def parse(v):
        return [int(x) for x in v.lstrip('v').split('.')]
    
    try:
        return parse(new_ver) > parse(current_ver)
    except ValueError:
        return new_ver != current_ver

def check_for_updates():
    """
    Checks for updates via Git or GitHub Tags.
    """
    # 1. Try Git First
    if is_git_repo():
        try:
            subprocess.run(["git", "fetch"], check=True, timeout=15, cwd=REPO_DIR)
            local = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_DIR).strip().decode()
            try:
                upstream = subprocess.check_output(["git", "rev-parse", "@{u}"], stderr=subprocess.DEVNULL, cwd=REPO_DIR).strip().decode()
            except:
                upstream = subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=REPO_DIR).strip().decode()
            
            remote = subprocess.check_output(["git", "rev-parse", upstream], cwd=REPO_DIR).strip().decode()
            
            if local == remote:
                return False, "You are up to date (Git)."
            
            count = subprocess.check_output(["git", "rev-list", "--count", "HEAD.."+upstream], cwd=REPO_DIR).strip().decode()
            if int(count) > 0:
                return True, f"Git Update available! ({count} commits behind)"
            return False, "Ahead of remote."
        except Exception as e:
            return False, f"Git check failed: {e}"

    # 2. Fallback to GitHub Tags
    tag, url = get_latest_tag()
    if tag:
        if compare_versions(tag, __version__):
            return True, f"New version {tag} available! (Current: {__version__})"
        return False, f"You are up to date ({__version__}). Latest: {tag}"
    
    return False, "Could not check for updates."

def perform_update():
    """
    Performs the update via Git Pull or Zip Download.
    """
    # 1. Git Update
    if is_git_repo():
        try:
            res = subprocess.run(["git", "pull", "--ff-only"], capture_output=True, text=True, cwd=REPO_DIR)
            if res.returncode == 0:
                return True, "Git pull successful! Restarting..."
            return False, f"Git pull failed: {res.stderr}"
        except Exception as e:
            return False, f"Error: {e}"

    # 2. Zip Update
    tag, zip_url = get_latest_tag()
    if not zip_url:
        return False, "Could not retrieve update URL."
    
    try:
        print(f"Downloading update from {zip_url}...")
        r = requests.get(zip_url, stream=True)
        r.raise_for_status()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                z.extractall(tmp_dir)
            
            # GitHub zips have a root folder like 'user-repo-hash'
            extracted_root = os.path.join(tmp_dir, os.listdir(tmp_dir)[0])
            
            # Overwrite files in REPO_DIR
            # We explicitly allow overwriting.
            # We iterate to avoid permissions issues with the root dir itself sometimes
            for item in os.listdir(extracted_root):
                s = os.path.join(extracted_root, item)
                d = os.path.join(REPO_DIR, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)
                    
        return True, f"Updated to {tag}! Restarting..."
        
    except Exception as e:
        return False, f"Update failed: {e}"

def restart_app():
    """Restarts the application."""
    python = sys.executable
    os.execl(python, python, *sys.argv)