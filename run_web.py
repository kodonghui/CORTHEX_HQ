#!/usr/bin/env python3
"""
CORTHEX HQ - 웹 서버 실행
==========================

이 파일을 실행하면 웹 브라우저에서 CEO 관제실을 사용할 수 있습니다.

실행 방법:
  python run_web.py

실행 후 웹 브라우저에서 http://localhost:8000 으로 접속하세요.
"""
import logging
import sys
import webbrowser
from threading import Timer

import uvicorn
from dotenv import load_dotenv


def open_browser() -> None:
    """서버 시작 후 자동으로 브라우저를 엽니다."""
    webbrowser.open("http://localhost:8000")


def main() -> None:
    """웹 서버를 시작합니다."""
    load_dotenv()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║       CORTHEX HQ - CEO 관제실 시작       ║")
    print("  ╠══════════════════════════════════════════╣")
    print("  ║                                          ║")
    print("  ║  웹 브라우저에서 아래 주소로 접속하세요:  ║")
    print("  ║  👉 http://localhost:8000                ║")
    print("  ║                                          ║")
    print("  ║  종료하려면 Ctrl+C 를 누르세요.          ║")
    print("  ╚══════════════════════════════════════════╝")
    print()

    # Auto-open browser after 1.5 seconds
    Timer(1.5, open_browser).start()

    try:
        uvicorn.run(
            "web.app:app",
            host="0.0.0.0",
            port=8000,
            reload=False,
            log_level="info",
        )
    except KeyboardInterrupt:
        print("\nCORTHEX HQ 웹 서버를 종료합니다.")
        sys.exit(0)


if __name__ == "__main__":
    main()
