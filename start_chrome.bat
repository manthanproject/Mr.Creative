@echo off
taskkill /F /IM chromedriver.exe >nul 2>&1
timeout /t 2 /nobreak >nul
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%~dp0chrome_pomelli_profile" https://labs.google.com/pomelli
