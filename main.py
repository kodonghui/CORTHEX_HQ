#!/usr/bin/env python3
"""
CORTHEX HQ - AI Agent Corporation
==================================

실행 방법:
  1. cp .env.example .env
  2. .env 파일에 API 키 입력
  3. pip install -e .
  4. python main.py

CEO(동희 님)로서 한국어로 명령을 내리면,
25명의 AI 에이전트 조직이 자동으로 업무를 처리합니다.
"""
import asyncio
import logging
import sys

from dotenv import load_dotenv


def setup_logging() -> None:
    """Configure logging for the application."""
    level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.FileHandler("corthex.log", encoding="utf-8"),
        ],
    )


def cli() -> None:
    """Main entry point."""
    load_dotenv()
    setup_logging()

    from src.cli.app import CorthexCLI

    app = CorthexCLI()
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("\nCORTHEX HQ를 종료합니다.")
        sys.exit(0)


if __name__ == "__main__":
    cli()
