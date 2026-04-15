@echo off
chcp 65001 >nul 2>&1
title 주식 호가창 분석 봇

echo ============================================
echo   주식 호가창 분석 봇 - 환경 설정
echo ============================================
echo.

:: .env 파일 확인
if not exist ".env" (
    echo [ERROR] .env 파일이 없습니다.
    echo .env.example을 복사하여 .env를 만들고 API 키를 입력하세요.
    pause
    exit /b 1
)

:: venv 확인 및 생성
if not exist ".venv\Scripts\activate.bat" (
    echo 가상환경을 생성합니다...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Python이 설치되어 있지 않습니다.
        echo https://www.python.org/downloads/ 에서 Python 3.12 이상을 설치하세요.
        pause
        exit /b 1
    )
    call .venv\Scripts\activate.bat
    echo 패키지를 설치합니다...
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

echo.
echo 봇을 시작합니다...
echo.

python run.py

echo.
pause
