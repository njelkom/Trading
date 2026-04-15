"""웹 UI 진입점 - Streamlit 서버 시작 + 브라우저 자동 열기"""
import subprocess
import sys
from pathlib import Path

APP_PATH = Path(__file__).parent / "src" / "presentation" / "web" / "streamlit_app.py"

if __name__ == "__main__":
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        str(APP_PATH),
        "--server.headless=false",
        "--browser.gatherUsageStats=false",
    ])
