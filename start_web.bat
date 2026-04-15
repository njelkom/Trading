@echo off
chcp 65001 >nul 2>&1
title 호가창 분석 봇 (웹)

if not exist ".env" (
    echo [ERROR] .env 파일이 없습니다.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\activate.bat" (
    echo 가상환경을 생성합니다...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

echo.
echo 웹 UI를 시작합니다... (브라우저가 자동으로 열립니다)
echo.

python run_web.py

pause
