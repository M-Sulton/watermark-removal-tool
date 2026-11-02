@echo off
title Watermark Removal Tool - Local Hardware Mode (Zero AI Token)
color 0B
echo ============================================================
echo   WATERMARK REMOVAL TOOL (LOCAL WINDOWS - 0 AI TOKEN)
echo   Render murni via CPU/GPU Laptop via OpenCV & FFmpeg
echo ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python belum terinstall di komputer ini!
    echo Silakan unduh Python dari https://www.python.org/downloads/
    echo Pastikan centang "Add Python to PATH" saat instalasi.
    pause
    exit /b
)

:: Check / Download FFmpeg standalone portable if not in PATH
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    if not exist "ffmpeg.exe" (
        echo [INFO] FFmpeg belum terpasang. Mengunduh FFmpeg portable untuk Windows...
        powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip -OutFile ffmpeg.zip"
        echo [INFO] Mengekstrak FFmpeg...
        powershell -Command "Expand-Archive -Path ffmpeg.zip -DestinationPath ffmpeg_temp -Force"
        powershell -Command "Copy-Item ffmpeg_temp*bin* -Destination . -Recurse -Force"
        powershell -Command "Remove-Item -Recurse -Force ffmpeg.zip, ffmpeg_temp"
        echo [OK] FFmpeg portable siap digunakan!
    )
)

:: Setup venv
if not exist "venv" (
    echo [INFO] Membuat virtual environment venv...
    python -m venv venv
)

echo [INFO] Mengaktifkan venv dan memeriksa dependencies...
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet --disable-pip-version-check

echo.
echo ============================================================
echo   Menjalankan server lokal di http://127.0.0.1:8000 ...
echo   Membuka browser otomatis...
echo   (JANGAN TUTUP JENDELA CMD INI SELAMA APLIKASI BERJALAN)
echo ============================================================
echo.

start "" http://127.0.0.1:8000
python main.py

pause
