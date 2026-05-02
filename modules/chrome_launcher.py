"""
Auto-launch Chrome with debug port if not already running.
"""
import subprocess
import socket
import time
import os


def is_port_open(port):
    """Check if a port is already in use (Chrome running)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(('127.0.0.1', port)) == 0


def launch_chrome(port, profile_dir, start_url=''):
    """Launch Chrome with debug port and profile if not already running."""
    if is_port_open(port):
        print(f"[ChromeLauncher] Chrome already running on port {port}")
        return True

    chrome_paths = [
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    ]
    chrome_exe = None
    for p in chrome_paths:
        if os.path.exists(p):
            chrome_exe = p
            break

    if not chrome_exe:
        print("[ChromeLauncher] Chrome not found!")
        return False

    # Make profile dir absolute
    if not os.path.isabs(profile_dir):
        profile_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), profile_dir)

    cmd = [
        chrome_exe,
        f'--remote-debugging-port={port}',
        f'--user-data-dir={profile_dir}',
    ]
    if start_url:
        cmd.append(start_url)

    print(f"[ChromeLauncher] Launching Chrome on port {port} with profile {os.path.basename(profile_dir)}...")
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Wait for port to open
    for _ in range(15):
        time.sleep(1)
        if is_port_open(port):
            print(f"[ChromeLauncher] Chrome ready on port {port}")
            return True

    print(f"[ChromeLauncher] Chrome failed to start on port {port}")
    return False


def ensure_pomelli_chrome(email=None):
    """Ensure Pomelli Chrome is running on port 9222 with the right profile."""
    # Map emails to profile folders
    profile_map = {
        'stocksmanthan@gmail.com': 'chrome_pomelli_stocksmanthan',
        'dropsyshops45@gmail.com': 'chrome_pomelli_dropsyshops45',
    }
    # Default profile
    profile = 'chrome_pomelli_profile'
    if email and email.lower() in profile_map:
        profile = profile_map[email.lower()]
    elif email:
        # Auto-generate profile name for new accounts
        safe_name = email.split('@')[0].replace('.', '_')
        profile = f'chrome_pomelli_{safe_name}'

    return launch_chrome(9222, profile, 'https://labs.google.com/pomelli')


def ensure_flow_chrome(email=None):
    """Ensure Flow Chrome is running on port 9223 with the right profile."""
    profile_map = {
        'crimsonbox69@gmail.com': 'chrome_flow_crimsonbox69',
    }
    profile = 'chrome_flow_profile'
    if email and email.lower() in profile_map:
        profile = profile_map[email.lower()]
    elif email:
        safe_name = email.split('@')[0].replace('.', '_')
        profile = f'chrome_flow_{safe_name}'

    return launch_chrome(9223, profile, 'https://labs.google/fx/tools/flow')


def ensure_gemini_chrome():
    """Ensure Gemini Chrome is running on port 9224 with its own profile."""
    return launch_chrome(9224, 'chrome_gemini', 'https://gemini.google.com')
