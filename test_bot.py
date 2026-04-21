from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os

# Connect to the already-open Chrome
options = Options()
options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

driver = webdriver.Chrome(options=options)
print(f"✓ Connected to Chrome: {driver.title}")
print(f"✓ URL: {driver.current_url}")

# Go to Pomelli
driver.get('https://labs.google.com/pomelli/')
time.sleep(5)
print(f"✓ On: {driver.current_url}")

# Enter prompt
textarea = WebDriverWait(driver, 15).until(
    EC.visibility_of_element_located((By.CSS_SELECTOR, 'textarea[placeholder*="Describe"]'))
)
textarea.clear()
for char in "Launch campaign for premium coffee brand with cozy winter theme":
    textarea.send_keys(char)
    time.sleep(0.03)
print("✓ Prompt entered")
time.sleep(2)

# Click Generate Ideas
gen_btn = WebDriverWait(driver, 15).until(
    EC.element_to_be_clickable((By.XPATH,
        '//button[.//span[contains(text(), "Generate Ideas")] or contains(text(), "Generate Ideas")]'))
)
gen_btn.click()
print("✓ Clicked Generate Ideas")

# Wait for idea cards
old_count = len(driver.find_elements(By.CSS_SELECTOR, 'button[aria-label="Delete idea"]'))
print("→ Waiting for ideas...")
for i in range(45):
    time.sleep(4)
    new_count = len(driver.find_elements(By.CSS_SELECTOR, 'button[aria-label="Delete idea"]'))
    if new_count - old_count >= 3:
        print(f"✓ Found {new_count - old_count} new ideas!")
        break
    print(f"  waiting... ({i*4}s)")

# Click first idea
time.sleep(2)
delete_btns = driver.find_elements(By.CSS_SELECTOR, 'button[aria-label="Delete idea"]')
if delete_btns:
    card = driver.execute_script("""
        let el = arguments[0];
        for (let i = 0; i < 10; i++) {
            el = el.parentElement;
            if (!el) break;
            if (el.tagName === 'MAT-CARD' || el.classList.contains('card') ||
                el.getAttribute('role') === 'button' || el.style.cursor === 'pointer') return el;
        }
        return arguments[0].parentElement.parentElement;
    """, delete_btns[0])
    if card:
        card.click()
        time.sleep(3)
        print(f"✓ Selected idea → {driver.current_url}")

# Wait for creatives
print("→ Waiting for creatives...")
for i in range(60):
    time.sleep(5)
    loading = driver.find_elements(By.XPATH,
        '//*[contains(text(), "minutes left") or contains(text(), "Taking longer") or contains(text(), "About")]')
    visible = [el for el in loading if el.is_displayed()]
    if not visible and i > 2:
        print("✓ All creatives loaded!")
        time.sleep(3)
        break
    print(f"  {len(visible)} still loading... ({i*5}s)")

# Download all creatives
print("\n→ Downloading creatives...")
download_dir = os.path.abspath('./static/downloads')
os.makedirs(download_dir, exist_ok=True)
existing = set(os.listdir(download_dir))

# Force download path
driver.execute_cdp_cmd('Page.setDownloadBehavior', {
    'behavior': 'allow', 'downloadPath': download_dir
})

# Find creative cards and download each
cards = driver.execute_script("""
    var all = document.querySelectorAll('*');
    var cards = [];
    for (var el of all) {
        var rect = el.getBoundingClientRect();
        if (rect.width > 200 && rect.height > 300 && rect.width < 500 && rect.top > 100) {
            var img = el.querySelector('img');
            if (img) cards.push(el);
        }
    }
    var unique = [];
    for (var c of cards) {
        var dup = false;
        for (var u of unique) { if (u.contains(c) || c.contains(u)) { dup = true; break; } }
        if (!dup) unique.push(c);
    }
    return unique;
""")
print(f"Found {len(cards)} creative cards")

downloaded = 0
for i, card in enumerate(cards):
    try:
        # Hover
        ActionChains(driver).move_to_element(card).perform()
        time.sleep(1)

        # Click top-right corner (3-dots position)
        w = driver.execute_script("return arguments[0].offsetWidth", card)
        h = driver.execute_script("return arguments[0].offsetHeight", card)
        ActionChains(driver).move_to_element_with_offset(card, w//2 - 15, -h//2 + 15).pause(1).click().perform()
        time.sleep(2)

        # Click 2nd menu item (Download)
        menu_items = WebDriverWait(driver, 5).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'button.mat-mdc-menu-item, [role="menuitem"]'))
        )
        if len(menu_items) >= 2:
            menu_items[1].click()
            downloaded += 1
            print(f"  ✓ Downloaded creative {downloaded}")
        time.sleep(3)

        # Move away
        ActionChains(driver).move_by_offset(-300, -300).perform()
        time.sleep(1)

    except Exception as e:
        print(f"  ✗ Skipped {i+1}: {str(e)[:50]}")
        try:
            driver.execute_script("document.querySelectorAll('.cdk-overlay-backdrop').forEach(el => el.click());")
        except:
            pass
        time.sleep(2)

print(f"\n✓ Downloaded {downloaded} creatives!")

# Check files
time.sleep(10)
new_files = set(os.listdir(download_dir)) - existing
print(f"✓ New files in downloads: {len(new_files)}")
for f in new_files:
    print(f"   {f}")

# Save to Mr.Creative collection
if new_files:
    print("\n→ Saving to Mr.Creative collection...")
    import requests as req

    MR_CREATIVE_URL = 'http://127.0.0.1:5000'

    # Login to Mr.Creative
    session = req.Session()
    login_resp = session.post(f'{MR_CREATIVE_URL}/login', data={
        'email': 'manthan@gmail.com',
        'password': '000000'
    }, allow_redirects=True)
    print(f"  Login status: {login_resp.status_code}")
    print(f"  Login URL: {login_resp.url}")

    # Create a new collection
    timestamp = time.strftime('%Y-%m-%d %H:%M')
    col_name = f"Pomelli Campaign - {timestamp}"
    create_resp = session.post(f'{MR_CREATIVE_URL}/collections/create', data={
        'name': col_name,
        'description': 'Auto-generated by Mr.Creative bot'
    }, allow_redirects=True)
    print(f"  Collection created: {create_resp.status_code}")

    # Upload each file to the collection
    # First find the collection ID from the page
    from bs4 import BeautifulSoup
    col_page = session.get(f'{MR_CREATIVE_URL}/collections/')
    # Extract collection ID from the page URL pattern
    import re
    col_ids = re.findall(r'/collections/([a-f0-9\-]{20,})', col_page.text)
    if col_ids:
        col_id = col_ids[0]
        print(f"  Collection ID: {col_id}")

        # Upload files
        for f in new_files:
            if f.endswith('.crdownload') or f.endswith('.tmp'):
                continue
            filepath = os.path.join(download_dir, f)
            with open(filepath, 'rb') as fp:
                files = {'files': (f, fp)}
                upload_resp = session.post(
                    f'{MR_CREATIVE_URL}/collections/{col_id}/upload',
                    files=files
                )
                if upload_resp.status_code == 200:
                    print(f"  ✓ Uploaded: {f}")
                else:
                    print(f"  ✗ Failed: {f}")

        print(f"\n✓ Collection '{col_name}' created with {len(new_files)} images!")
        print(f"  View at: {MR_CREATIVE_URL}/collections/{col_id}")
    else:
        print("  ✗ Could not find collection ID")

print("\n✓ DONE! Browser stays open.")