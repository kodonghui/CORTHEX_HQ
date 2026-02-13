"""
Git auto-sync utility for CORTHEX HQ config files.

웹 UI에서 설정 변경 시 자동으로 git add + commit + push 실행.
이벤트 루프를 차단하지 않도록 스레드 풀에서 실행한다.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger("corthex.git_sync")


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

    # repo root 탐색
    repo_dir = file_path.parent
    while repo_dir != repo_dir.parent:
        if (repo_dir / ".git").exists():
            break
        repo_dir = repo_dir.parent
    else:
        return {"success": False, "message": "Git 저장소를 찾을 수 없습니다"}

    def _run_git() -> dict[str, Any]:
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
    return await loop.run_in_executor(None, _run_git)
