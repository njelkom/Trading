#!/bin/bash
echo "============================================"
echo "  주식 호가창 분석 봇 - 환경 설정"
echo "============================================"
echo

# .env 파일 확인
if [ ! -f ".env" ]; then
    echo "[ERROR] .env 파일이 없습니다."
    echo ".env.example을 복사하여 .env를 만들고 API 키를 입력하세요."
    exit 1
fi

# venv 확인 및 생성
if [ ! -d ".venv" ]; then
    echo "가상환경을 생성합니다..."
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo "[ERROR] Python 3이 설치되어 있지 않습니다."
        exit 1
    fi
    source .venv/bin/activate
    echo "패키지를 설치합니다..."
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

echo
echo "봇을 시작합니다..."
echo

python3 run.py
