"""
코드 품질 검사 Tool.

bandit(보안), ruff(린팅), pytest(테스트)를 실행하여
코드 품질을 검사하고 결과를 분석합니다.

사용 방법:
  - action="security": 보안 취약점 검사 (bandit)
  - action="lint": 코드 스타일/품질 검사 (ruff)
  - action="test": 테스트 실행 (pytest)
  - action="all": 보안 + 린트 + 테스트 모두 실행

필요 환경변수: 없음 (bandit, ruff는 pip install 필요)
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.code_quality")

# 프로젝트 루트 기준 검사 대상
DEFAULT_TARGET = "src/"


class CodeQualityTool(BaseTool):
    """코드 품질 검사 도구."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "all")

        if action == "security":
            return await self._run_security(kwargs)
        elif action == "lint":
            return await self._run_lint(kwargs)
        elif action == "test":
            return await self._run_test(kwargs)
        elif action == "all":
            return await self._run_all(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "security, lint, test, all 중 하나를 사용하세요."
            )

    # ── 보안 검사 (bandit) ──

    async def _run_security(self, kwargs: dict[str, Any]) -> str:
        if not shutil.which("bandit"):
            return (
                "bandit이 설치되지 않았습니다.\n"
                "설치: pip install bandit"
            )

        target = kwargs.get("target", DEFAULT_TARGET)
        cmd = ["bandit", "-r", target, "-f", "txt", "--severity-level", "medium"]

        result = await self._run_cmd(cmd, timeout=60)
        output = result.stdout + result.stderr

        if result.returncode == 0:
            summary = "보안 취약점 없음 (PASS)"
        else:
            summary = "보안 취약점 발견"

        formatted = f"### 보안 검사 (bandit)\n결과: {summary}\n\n{output[:3000]}"

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 보안 코드 리뷰 전문가입니다.\n"
                "bandit 보안 검사 결과를 분석하여 다음을 정리하세요:\n"
                "1. 발견된 취약점 수와 심각도별 분류\n"
                "2. 주요 취약점 설명 (비개발자도 이해할 수 있게)\n"
                "3. 수정 우선순위 및 방법 제안\n"
                "한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## 보안 검사\n\n{formatted}\n\n---\n\n## 분석\n\n{analysis}"

    # ── 린트 검사 (ruff) ──

    async def _run_lint(self, kwargs: dict[str, Any]) -> str:
        if not shutil.which("ruff"):
            return (
                "ruff가 설치되지 않았습니다.\n"
                "설치: pip install ruff"
            )

        target = kwargs.get("target", DEFAULT_TARGET)
        cmd = ["ruff", "check", target, "--output-format", "text"]

        result = await self._run_cmd(cmd, timeout=60)
        output = result.stdout + result.stderr

        if result.returncode == 0:
            summary = "코드 스타일 문제 없음 (PASS)"
        else:
            # 문제 건수 추출
            lines = output.strip().split("\n")
            issue_count = len([l for l in lines if l.strip() and ":" in l])
            summary = f"코드 스타일 문제 {issue_count}건 발견"

        formatted = f"### 린트 검사 (ruff)\n결과: {summary}\n\n{output[:3000]}"

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 코드 품질 리뷰 전문가입니다.\n"
                "ruff 린트 검사 결과를 분석하여 다음을 정리하세요:\n"
                "1. 주요 문제 유형별 분류 (미사용 import, 코딩 스타일 등)\n"
                "2. 심각도별 분류 (수정 필수 vs 권장)\n"
                "3. 코드 품질 등급 (A~F)\n"
                "한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## 린트 검사\n\n{formatted}\n\n---\n\n## 분석\n\n{analysis}"

    # ── 테스트 실행 (pytest) ──

    async def _run_test(self, kwargs: dict[str, Any]) -> str:
        if not shutil.which("pytest"):
            return (
                "pytest가 설치되지 않았습니다.\n"
                "설치: pip install pytest"
            )

        cmd = ["pytest", "--tb=short", "-q"]
        target = kwargs.get("target", "")
        if target:
            cmd.append(target)

        result = await self._run_cmd(cmd, timeout=300)
        output = result.stdout + result.stderr

        if result.returncode == 0:
            summary = "모든 테스트 통과 (PASS)"
        elif result.returncode == 5:
            summary = "테스트 파일이 없습니다"
        else:
            summary = "테스트 실패"

        formatted = f"### 테스트 (pytest)\n결과: {summary}\n\n{output[:3000]}"

        return f"## 테스트 결과\n\n{formatted}"

    # ── 전체 실행 ──

    async def _run_all(self, kwargs: dict[str, Any]) -> str:
        results = []

        security = await self._run_security(kwargs)
        results.append(security)

        lint = await self._run_lint(kwargs)
        results.append(lint)

        test = await self._run_test(kwargs)
        results.append(test)

        return "\n\n" + "=" * 60 + "\n\n".join(results)

    # ── 커맨드 실행 헬퍼 ──

    async def _run_cmd(self, cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
        """명령어를 비동기로 실행."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=".",
            )
            return result
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(
                cmd, returncode=1,
                stdout="", stderr=f"타임아웃: {timeout}초 초과",
            )
        except FileNotFoundError:
            return subprocess.CompletedProcess(
                cmd, returncode=1,
                stdout="", stderr=f"명령어를 찾을 수 없음: {cmd[0]}",
            )
