import requests
import os
import hashlib
from pathlib import Path
import subprocess
import sys

# ================= CONFIG =================
BASE_URL = "https://raw.githubusercontent.com/Majnik999/discord-all-in-one-bot_nexusbot/main/"
REPO_PATH = Path(__file__).parent
UPDATER_FILE = Path(__file__).name
MAIN_SCRIPT = "main.py"  # The script to run if no updates
# ==========================================

def file_hash(path):
    """Return SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def download_file(remote_path):
    """Download a file from BASE_URL and return bytes."""
    url = BASE_URL + remote_path.as_posix()
    try:
        r = requests.get(url)
        r.raise_for_status()
        return r.content
    except requests.RequestException as e:
        print(f"Failed to download {remote_path}: {e}")
        return None

def get_remote_file_list():
    """
    Fetch a list of files from files.txt hosted in the repo.
    Each line should be a relative path.
    """
    try:
        r = requests.get(BASE_URL + "files.txt")
        r.raise_for_status()
        return [Path(line.strip()) for line in r.text.splitlines() if line.strip()]
    except Exception as e:
        print("Failed to fetch files.txt:", e)
        return []

def update_files():
    remote_files = get_remote_file_list()
    updated = False

    for file in remote_files:
        # Skip the updater itself
        if file.name == UPDATER_FILE:
            continue

        local_path = REPO_PATH / file
        remote_content = download_file(file)
        if remote_content is None:
            continue

        # Check hash
        if local_path.exists():
            local_hash = file_hash(local_path)
            remote_hash = hashlib.sha256(remote_content).hexdigest()
            if local_hash == remote_hash:
                continue

        # Ensure directories exist
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(remote_content)
        print(f"Updated: {file}")
        updated = True

    return updated

if __name__ == "__main__":
    updated = update_files()
    if updated:
        print("Files were updated. Please restart the program.")
        sys.exit(0)  # Exit without running main.py
    else:
        print("All files are up-to-date. Launching main script...")
        # Run the main script
        subprocess.run([sys.executable, str(REPO_PATH / MAIN_SCRIPT)])
