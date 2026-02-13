"""
Git 자동 동기화 모듈.

1) auto_push_reports: 보고서(reports/) 자동 git push
2) git_auto_sync: 웹 UI 설정 변경 시 개별 파일 git push
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger("corthex.git_sync")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ── 1) 보고서 자동 업로드 ─────────────────────────────────────

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


async def auto_push_reports(command: str) -> bool:
    """reports/ 전체를 git add → commit → push. 성공 시 True 반환."""
    if not _is_git_repo():
        logger.warning("git 저장소가 아닙니다. 자동 업로드를 건너뜁니다.")
        return False

    if not _auto_upload_enabled():
        logger.info("CORTHEX_AUTO_UPLOAD=0 — 자동 업로드 비활성화.")
        return False

    try:
        rc, out = await _run_git("add", "reports/")
        if rc != 0:
            logger.error("git add 실패: %s", out)
            return False

        msg = f"report: {command[:60]}"
        rc, out = await _run_git("commit", "-m", msg)
        if rc != 0:
            if "nothing to commit" in out:
                logger.info("변경 사항 없음, 커밋 건너뜀.")
                return True
            logger.error("git commit 실패: %s", out)
            return False

        pushed = await _push_with_retry()
        if pushed:
            logger.info("GitHub 자동 업로드 완료: reports/")
        return pushed

    except Exception as e:
        logger.error("git 자동 동기화 실패: %s", e)
        return False


async def _push_with_retry(max_retries: int = 4) -> bool:
    """push 실패 시 exponential backoff으로 재시도."""
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


# ── 2) 웹 UI 설정 변경 동기화 ─────────────────────────────────

async def git_auto_sync(
    file_path: Path,
    commit_message: str = "",
) -> dict[str, Any]:
    """
    지정된 파일을 git add → commit → push 한다.

    Returns:
        {"success": bool, "message": str}
    """
    if not commit_message:
        commit_message = f"[CORTHEX HQ] 설정 변경: {file_path.name}"

    repo_dir = file_path.parent
    while repo_dir != repo_dir.parent:
        if (repo_dir / ".git").exists():
            break
        repo_dir = repo_dir.parent
    else:
        return {"success": False, "message": "Git 저장소를 찾을 수 없습니다"}

    def _run_git_sync() -> dict[str, Any]:
        try:
            subprocess.run(
                ["git", "add", str(file_path)],
                cwd=str(repo_dir),
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=str(repo_dir),
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            subprocess.run(
                ["git", "push"],
                cwd=str(repo_dir),
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            logger.info("Git sync 완료: %s", commit_message)
            return {"success": True, "message": "Git 동기화 완료"}
        except subprocess.CalledProcessError as e:
            err = (e.stderr or e.stdout or str(e)).strip()
            logger.warning("Git sync 실패: %s", err)
            return {"success": False, "message": err}
        except Exception as e:
            logger.warning("Git sync 오류: %s", e)
            return {"success": False, "message": str(e)}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_git_sync)
