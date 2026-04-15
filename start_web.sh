#!/bin/bash
echo "웹 UI를 시작합니다... (브라우저가 자동으로 열립니다)"

if [ ! -f ".env" ]; then
    echo "[ERROR] .env 파일이 없습니다."
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "가상환경을 생성합니다..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

python3 run_web.py
