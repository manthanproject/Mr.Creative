@echo off
echo [Mr.Creative] Killing old Chrome/ChromeDriver instances...
taskkill /F /IM chromedriver.exe >nul 2>&1
taskkill /F /IM chrome.exe >nul 2>&1
timeout /t 3 /nobreak >nul

echo [Mr.Creative] Starting Pomelli Chrome (port 9222)...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%~dp0chrome_pomelli_profile" https://labs.google.com/pomelli

timeout /t 2 /nobreak >nul

echo [Mr.Creative] Starting Flow Chrome (port 9223)...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9223 --user-data-dir="%~dp0chrome_flow_profile" https://labs.google/fx/tools/flow

echo [Mr.Creative] Both Chrome instances running!
echo   Pomelli: port 9222
echo   Flow:    port 9223
echo.
echo Close this window or press any key to exit.
pause >nul
