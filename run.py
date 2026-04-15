"""진입점 - 프로젝트 루트에서 실행"""
import asyncio
import sys
import warnings
from src.main import main

if __name__ == "__main__":
    # asyncio 종료 시 불필요한 경고 숨김
    warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*coroutine.*")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        print("\n봇이 정상 종료되었습니다.")
        sys.exit(0)
