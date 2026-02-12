"""
Git 자동 동기화 모듈.

보고서가 저장되면 자동으로 git add → commit → push를 수행합니다.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger("corthex.git_sync")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


async def _run_git(*args: str) -> tuple[int, str]:
    """git 명령을 비동기로 실행하고 (returncode, stdout) 반환."""
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=str(REPO_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    output = stdout.decode("utf-8", errors="replace").strip()
    return proc.returncode, output


async def auto_push(filepath: Path, command: str) -> bool:
    """파일을 git add → commit → push. 성공 시 True 반환."""
    if not _is_git_repo():
        logger.warning("git 저장소가 아닙니다. 자동 업로드를 건너뜁니다.")
        return False

    if not _auto_upload_enabled():
        logger.info("CORTHEX_AUTO_UPLOAD=0 — 자동 업로드 비활성화.")
        return False

    try:
        # git add
        rel_path = filepath.relative_to(REPO_ROOT)
        rc, out = await _run_git("add", str(rel_path))
        if rc != 0:
            logger.error("git add 실패: %s", out)
            return False

        # git commit
        msg = f"report: {command[:60]}"
        rc, out = await _run_git("commit", "-m", msg)
        if rc != 0:
            if "nothing to commit" in out:
                logger.info("변경 사항 없음, 커밋 건너뜀.")
                return True
            logger.error("git commit 실패: %s", out)
            return False

        # git push (with retry)
        pushed = await _push_with_retry()
        if pushed:
            logger.info("GitHub 자동 업로드 완료: %s", rel_path)
        return pushed

    except Exception as e:
        logger.error("git 자동 동기화 실패: %s", e)
        return False


async def _push_with_retry(max_retries: int = 4) -> bool:
    """push 실패 시 exponential backoff으로 재시도."""
    # 현재 브랜치 이름 가져오기
    rc, branch = await _run_git("rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0:
        branch = "main"

    for attempt in range(max_retries):
        rc, out = await _run_git("push", "-u", "origin", branch)
        if rc == 0:
            return True

        wait = 2 ** (attempt + 1)  # 2, 4, 8, 16
        logger.warning("push 실패 (시도 %d/%d), %d초 후 재시도: %s",
                        attempt + 1, max_retries, wait, out)
        await asyncio.sleep(wait)

    logger.error("push 최종 실패 (%d회 시도)", max_retries)
    return False


def _is_git_repo() -> bool:
    """REPO_ROOT가 git 저장소인지 확인."""
    return (REPO_ROOT / ".git").is_dir()


def _auto_upload_enabled() -> bool:
    """환경변수로 자동 업로드 ON/OFF 제어. 기본값: ON."""
    return os.getenv("CORTHEX_AUTO_UPLOAD", "1") != "0"
