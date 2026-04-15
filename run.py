"""진입점 - 프로젝트 루트에서 실행"""
import asyncio
import os
import signal
import sys

from src.main import main


def _force_exit(*_):
    """Ctrl+C 시 즉시 종료"""
    print("\n\n봇이 정상 종료되었습니다.")
    os._exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _force_exit)
    signal.signal(signal.SIGTERM, _force_exit)

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        _force_exit()
