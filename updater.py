import requests
import hashlib
import sys
import subprocess
from pathlib import Path

# ================= CONFIG =================
# Your GitHub repository raw URL (main branch)
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/Majnik999/NexusBot/main/"
REPO_PATH = Path(__file__).parent
UPDATER_FILE = Path(__file__).name
MAIN_SCRIPT = "main.py"  # Script to run if no updates
# ==========================================

def get_remote_file_content(path: str):
    """Download a file from GitHub and return bytes, or None if failed"""
    url = GITHUB_RAW_BASE + path
    try:
        r = requests.get(url)
        r.raise_for_status()
        return r.content
    except Exception as e:
        print(f"Failed to download {path}: {e}")
        return None

def file_hash(path: Path):
    """Return SHA256 hash of a local file"""
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def list_github_files(path=""):
    """
    Recursively list all files in the repo using GitHub API.
    This requires the repo to be public.
    """
    import requests
    import os

    # Transform raw URL to API URL
    user_repo = GITHUB_RAW_BASE.replace("https://raw.githubusercontent.com/", "").split("/")
    if len(user_repo) < 2:
        print("Invalid GitHub raw URL format")
        return []

    owner = user_repo[0]
    repo = user_repo[1]
    branch = user_repo[2] if len(user_repo) > 2 else "main"

    api_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"

    try:
        r = requests.get(api_url)
        r.raise_for_status()
        data = r.json()
        files = [item['path'] for item in data['tree'] if item['type'] == 'blob']
        return files
    except Exception as e:
        print("Failed to list GitHub files:", e)
        return []

def update_all_files():
    files = list_github_files()
    if not files:
        print("No files found on GitHub.")
        return False

    updated = False
    for file_path in files:
        if Path(file_path).name == UPDATER_FILE:
            continue  # Skip updater itself

        local_file = REPO_PATH / file_path
        remote_content = get_remote_file_content(file_path)
        if remote_content is None:
            continue

        local_hash = file_hash(local_file)
        remote_hash = hashlib.sha256(remote_content).hexdigest()

        if local_hash != remote_hash:
            # Ensure directories exist
            local_file.parent.mkdir(parents=True, exist_ok=True)
            with open(local_file, "wb") as f:
                f.write(remote_content)
            print(f"Updated: {file_path}")
            updated = True

    return updated

if __name__ == "__main__":
    updated = update_all_files()
    if updated:
        print("Files were updated. Please restart the program.")
        sys.exit(0)
    else:
        print("All files are up-to-date. Launching main script...")
        subprocess.run([sys.executable, str(REPO_PATH / MAIN_SCRIPT)])
