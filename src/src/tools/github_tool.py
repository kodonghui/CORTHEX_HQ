"""
GitHub API Tool.

GitHub REST API를 사용하여 이슈, PR, 커밋 이력,
저장소 통계를 조회합니다.

사용 방법:
  - action="issues": 이슈 목록/상세 조회
  - action="prs": PR 목록/상세 조회
  - action="commits": 최근 커밋 이력
  - action="repo_stats": 저장소 통계 (스타, 포크 등)

필요 환경변수:
  - GITHUB_TOKEN: GitHub Personal Access Token
  - GITHUB_REPO: 대상 저장소 (기본값: kodonghui/CORTHEX_HQ)
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.github_tool")

GITHUB_API = "https://api.github.com"


class GithubTool(BaseTool):
    """GitHub 저장소 관리 도구."""

    @property
    def _repo(self) -> str:
        return os.getenv("GITHUB_REPO", "kodonghui/CORTHEX_HQ")

    @property
    def _headers(self) -> dict[str, str]:
        token = os.getenv("GITHUB_TOKEN", "")
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "issues")

        if action == "issues":
            return await self._get_issues(kwargs)
        elif action == "prs":
            return await self._get_prs(kwargs)
        elif action == "commits":
            return await self._get_commits(kwargs)
        elif action == "repo_stats":
            return await self._get_repo_stats(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "issues, prs, commits, repo_stats 중 하나를 사용하세요."
            )

    # ── 이슈 조회 ──

    async def _get_issues(self, kwargs: dict[str, Any]) -> str:
        state = kwargs.get("state", "open")  # open, closed, all
        labels = kwargs.get("labels", "")
        per_page = int(kwargs.get("size", 10))

        params: dict[str, str] = {
            "state": state,
            "per_page": str(per_page),
            "sort": "updated",
            "direction": "desc",
        }
        if labels:
            params["labels"] = labels

        data = await self._api_get(f"/repos/{self._repo}/issues", params)
        if isinstance(data, str):
            return data  # 에러 메시지

        # PR은 제외 (GitHub API는 이슈에 PR도 포함)
        issues = [i for i in data if "pull_request" not in i]

        if not issues:
            return f"'{self._repo}' 저장소에 {state} 상태 이슈가 없습니다."

        lines = [f"### GitHub 이슈 ({state}) — {self._repo}"]
        for issue in issues:
            labels_str = ", ".join(l["name"] for l in issue.get("labels", []))
            lines.append(
                f"  #{issue['number']} {issue['title']}\n"
                f"    상태: {issue['state']} | "
                f"작성자: {issue.get('user', {}).get('login', '')} | "
                f"라벨: {labels_str or '없음'}\n"
                f"    업데이트: {issue.get('updated_at', '')[:10]}"
            )

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 프로젝트 관리 전문가입니다.\n"
                "GitHub 이슈를 분석하여 다음을 정리하세요:\n"
                "1. 현재 이슈 현황 요약 (건수, 주요 카테고리)\n"
                "2. 우선적으로 해결해야 할 이슈 top 3\n"
                "3. 전체적인 프로젝트 건강 상태 평가\n"
                "한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## GitHub 이슈\n\n{formatted}\n\n---\n\n## 분석\n\n{analysis}"

    # ── PR 조회 ──

    async def _get_prs(self, kwargs: dict[str, Any]) -> str:
        state = kwargs.get("state", "open")
        per_page = int(kwargs.get("size", 10))

        data = await self._api_get(
            f"/repos/{self._repo}/pulls",
            {"state": state, "per_page": str(per_page), "sort": "updated", "direction": "desc"},
        )
        if isinstance(data, str):
            return data

        if not data:
            return f"'{self._repo}' 저장소에 {state} 상태 PR이 없습니다."

        lines = [f"### GitHub PR ({state}) — {self._repo}"]
        for pr in data:
            lines.append(
                f"  #{pr['number']} {pr['title']}\n"
                f"    작성자: {pr.get('user', {}).get('login', '')} | "
                f"브랜치: {pr.get('head', {}).get('ref', '')} → {pr.get('base', {}).get('ref', '')}\n"
                f"    업데이트: {pr.get('updated_at', '')[:10]}"
            )

        return "\n".join(lines)

    # ── 커밋 이력 ──

    async def _get_commits(self, kwargs: dict[str, Any]) -> str:
        per_page = int(kwargs.get("size", 15))
        branch = kwargs.get("branch", "")

        params: dict[str, str] = {"per_page": str(per_page)}
        if branch:
            params["sha"] = branch

        data = await self._api_get(f"/repos/{self._repo}/commits", params)
        if isinstance(data, str):
            return data

        if not data:
            return "커밋 이력이 없습니다."

        lines = [f"### 최근 커밋 이력 — {self._repo}"]
        for commit in data:
            sha = commit.get("sha", "")[:7]
            msg = commit.get("commit", {}).get("message", "").split("\n")[0]
            author = commit.get("commit", {}).get("author", {}).get("name", "")
            date = commit.get("commit", {}).get("author", {}).get("date", "")[:10]
            lines.append(f"  {sha} {date} [{author}] {msg}")

        return "\n".join(lines)

    # ── 저장소 통계 ──

    async def _get_repo_stats(self, kwargs: dict[str, Any]) -> str:
        data = await self._api_get(f"/repos/{self._repo}", {})
        if isinstance(data, str):
            return data

        lines = [f"### 저장소 통계 — {self._repo}"]
        lines.append(f"  설명: {data.get('description', '없음')}")
        lines.append(f"  스타: {data.get('stargazers_count', 0)}")
        lines.append(f"  포크: {data.get('forks_count', 0)}")
        lines.append(f"  열린 이슈: {data.get('open_issues_count', 0)}")
        lines.append(f"  기본 브랜치: {data.get('default_branch', 'main')}")
        lines.append(f"  언어: {data.get('language', '없음')}")
        lines.append(f"  생성일: {data.get('created_at', '')[:10]}")
        lines.append(f"  마지막 푸시: {data.get('pushed_at', '')[:10]}")
        lines.append(f"  크기: {data.get('size', 0):,} KB")

        return "\n".join(lines)

    # ── API 호출 헬퍼 ──

    async def _api_get(self, path: str, params: dict[str, str]) -> Any:
        """GitHub REST API GET 요청."""
        if not os.getenv("GITHUB_TOKEN"):
            return (
                "GITHUB_TOKEN이 설정되지 않았습니다.\n"
                "GitHub(https://github.com/settings/tokens)에서 "
                "Personal Access Token을 발급받은 뒤 .env에 추가하세요.\n"
                "예: GITHUB_TOKEN=ghp_your-token"
            )

        url = f"{GITHUB_API}{path}"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    url, headers=self._headers, params=params, timeout=15,
                )
        except httpx.HTTPError as e:
            return f"GitHub API 호출 실패: {e}"

        if resp.status_code == 401:
            return "GitHub API 인증 실패 (401). GITHUB_TOKEN을 확인하세요."
        if resp.status_code == 404:
            return f"저장소 '{self._repo}'를 찾을 수 없습니다. GITHUB_REPO를 확인하세요."
        if resp.status_code != 200:
            return f"GitHub API 오류 ({resp.status_code}): {resp.text[:200]}"

        return resp.json()
