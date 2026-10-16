@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   Сборка Game Screenshoter v1.0.0
echo ============================================================
echo.

echo [1/6] Останавливаю процессы...
taskkill /f /im GameScreenshoter.exe 2>nul
timeout /t 2 /nobreak >nul

echo [2/6] Чищу старые сборки...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist __pycache__ rmdir /s /q __pycache__
if exist GameScreenshoter.spec del /q GameScreenshoter.spec
if exist portable rmdir /s /q portable

echo [3/6] Собираю EXE...
python -m PyInstaller --noconfirm --onefile --windowed --icon=assets/icon.ico --name=GameScreenshoter --add-data "assets;assets" screenshoter.py

if not exist dist\GameScreenshoter.exe (
    echo.
    echo !!! ОШИБКА: EXE не собрался !!!
    pause
    exit /b 1
)

echo.
echo [4/6] Готовлю портативную версию...
mkdir portable
copy dist\GameScreenshoter.exe portable\ >nul
xcopy assets portable\assets\ /E /I /Y >nul
copy license.txt portable\LICENSE.txt >nul
copy README.md portable\README.md >nul

echo [5/6] Собираю ZIP для GitHub...
if not exist Output mkdir Output
powershell -NoProfile -Command "Compress-Archive -Path 'portable\*' -DestinationPath 'Output\GameScreenshoter_Portable_v1.0.0.zip' -Force"

echo [6/6] Убираю временную папку portable...
rmdir /s /q portable

echo.
echo ============================================================
echo   ГОТОВО!
echo ============================================================
echo.
echo   Портативная версия: Output\GameScreenshoter_Portable_v1.0.0.zip
echo   Установщик:         теперь открой installer.iss в Inno Setup и нажми F9
echo.
pause