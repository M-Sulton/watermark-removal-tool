@echo off
title Watermark Removal Tool - Local
color 0A
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    start "" http://127.0.0.1:8000
    python main.py
) else (
    call install_and_run.bat
)
