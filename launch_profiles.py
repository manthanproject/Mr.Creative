import json
import os
import subprocess
import glob

CHROME_USER_DATA = os.path.expanduser(r'~\AppData\Local\Google\Chrome\User Data')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

def find_profiles_with_extension():
    """Scan all Chrome profiles to find ones with Mr.Creative extension installed."""
    profiles = []
    dirs = ['Default'] + [os.path.basename(d) for d in glob.glob(os.path.join(CHROME_USER_DATA, 'Profile *'))]

    for profile_dir in dirs:
        ext_path = os.path.join(CHROME_USER_DATA, profile_dir, 'Extensions')
        prefs_path = os.path.join(CHROME_USER_DATA, profile_dir, 'Preferences')

        if not os.path.exists(ext_path) or not os.path.exists(prefs_path):
            continue

        has_extension = False
        for ext_id_dir in os.listdir(ext_path):
            ext_versions = os.path.join(ext_path, ext_id_dir)
            if os.path.isdir(ext_versions):
                for version_dir in os.listdir(ext_versions):
                    manifest = os.path.join(ext_versions, version_dir, 'manifest.json')
                    if os.path.exists(manifest):
                        try:
                            with open(manifest, encoding='utf-8') as f:
                                data = json.load(f)
                            if data.get('name') == 'Mr.Creative Bot':
                                has_extension = True
                                break
                        except:
                            pass
                if has_extension:
                    break

        if not has_extension:
            continue

        email = 'unknown'
        try:
            with open(prefs_path, encoding='utf-8') as f:
                prefs = json.load(f)
            email = prefs.get('account_info', [{}])[0].get('email', '')
        except:
            pass

        profiles.append({'profile_dir': profile_dir, 'account': email or 'unknown'})

    return profiles

def launch():
    profiles = find_profiles_with_extension()
    if not profiles:
        print('No Chrome profiles with Mr.Creative extension found.')
        print('Install the extension in chrome://extensions/ first.')
        return

    print(f'Found {len(profiles)} profiles with Mr.Creative extension:')
    for p in profiles:
        print(f"  Launching: {p['account']} ({p['profile_dir']})")
        subprocess.Popen([CHROME, f'--profile-directory={p["profile_dir"]}',
                         'https://labs.google.com/pomelli/campaigns'])
    print('All profiles launched!')

if __name__ == '__main__':
    launch()
