"""
보안 취약점 스캐너 도구 (Security Scanner).

프로젝트 의존성 패키지의 알려진 보안 취약점(CVE)을 검사합니다.
pip-audit 또는 OSV API를 통해 취약점을 식별하고
해결 방법을 제안합니다.

사용 방법:
  - action="scan": requirements.txt 기반 전체 취약점 스캔
  - action="check_package": 특정 패키지 취약점 확인 (package, version)
  - action="report": 전체 보안 보고서 (LLM 분석 포함)

필요 환경변수: 없음
의존 라이브러리: httpx (OSV API용)
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.security_scanner")

OSV_API_URL = "https://api.osv.dev/v1/query"
PYPI_API_URL = "https://pypi.org/pypi"


class SecurityScannerTool(BaseTool):
    """보안 취약점 스캐너 — 프로젝트 의존성의 알려진 CVE를 검사합니다."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "scan")

        if action == "scan":
            return await self._scan(kwargs)
        elif action == "check_package":
            return await self._check_package(kwargs)
        elif action == "report":
            return await self._full_report(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "scan, check_package, report 중 하나를 사용하세요."
            )

    # ── requirements.txt 파싱 ──

    @staticmethod
    def _parse_requirements(file_path: str) -> list[tuple[str, str]]:
        """requirements.txt에서 패키지명과 버전을 추출합니다."""
        packages: list[tuple[str, str]] = []
        path = Path(file_path)
        if not path.exists():
            return packages

        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            if "==" in line:
                name, version = line.split("==", 1)
                packages.append((name.strip(), version.strip()))
            elif ">=" in line:
                name = line.split(">=")[0].strip()
                packages.append((name.strip(), "latest"))
            elif "~=" in line:
                name, version = line.split("~=", 1)
                packages.append((name.strip(), version.strip()))
            else:
                # 버전 지정 없는 경우
                name = line.split("[")[0].strip()  # extras 제거
                if name:
                    packages.append((name, "latest"))
        return packages

    # ── pip-audit 실행 ──

    @staticmethod
    def _try_pip_audit(requirements_file: str) -> dict | None:
        """pip-audit가 설치되어 있으면 실행합니다. 없으면 None 반환."""
        try:
            result = subprocess.run(
                ["pip-audit", "--format=json", "-r", requirements_file],
                capture_output=True,
                text=True,
                timeout=120,
            )
            return json.loads(result.stdout) if result.stdout.strip() else None
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return None

    # ── OSV API 조회 ──

    async def _query_osv(self, package: str, version: str) -> list[dict]:
        """OSV API로 특정 패키지의 취약점을 조회합니다."""
        body: dict[str, Any] = {
            "package": {"name": package, "ecosystem": "PyPI"},
        }
        if version and version != "latest":
            body["version"] = version

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    OSV_API_URL, json=body, timeout=15,
                )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("vulns", [])
        except Exception as exc:
            logger.warning("OSV API 조회 실패 (%s): %s", package, exc)
        return []

    # ── PyPI API 조회 ──

    async def _query_pypi(self, package: str, version: str) -> list[dict]:
        """PyPI JSON API로 취약점 정보를 조회합니다."""
        url = f"{PYPI_API_URL}/{package}/{version}/json" if version != "latest" else f"{PYPI_API_URL}/{package}/json"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("vulnerabilities", [])
        except Exception as exc:
            logger.warning("PyPI API 조회 실패 (%s): %s", package, exc)
        return []

    # ── 취약점 심각도 판별 ──

    @staticmethod
    def _severity_label(vuln: dict) -> tuple[str, str]:
        """취약점의 심각도 레벨과 이모지를 반환합니다."""
        severity = ""
        # OSV 형식
        for s in vuln.get("severity", []):
            score_str = s.get("score", "")
            if score_str:
                try:
                    score = float(score_str)
                    if score >= 7.0:
                        return "🔴", "높음"
                    elif score >= 4.0:
                        return "🟡", "중간"
                    else:
                        return "🟢", "낮음"
                except ValueError:
                    pass
        # 키워드 기반 추정
        details = json.dumps(vuln, ensure_ascii=False).lower()
        if any(w in details for w in ["critical", "high", "심각", "인증", "주입"]):
            return "🔴", "높음"
        elif any(w in details for w in ["medium", "moderate", "중간"]):
            return "🟡", "중간"
        return "🟢", "낮음"

    # ── action 구현 ──

    async def _scan(self, kwargs: dict[str, Any]) -> str:
        """requirements.txt 기반 전체 스캔."""
        req_file = kwargs.get("requirements_file", "requirements.txt")
        packages = self._parse_requirements(req_file)

        if not packages:
            return f"패키지를 찾을 수 없습니다. '{req_file}' 파일을 확인하세요."

        # 1차: pip-audit 시도
        audit_result = self._try_pip_audit(req_file)
        if audit_result is not None:
            return self._format_pip_audit(audit_result, len(packages))

        # 2차: OSV API fallback
        vulnerabilities: list[dict[str, Any]] = []
        for pkg_name, pkg_version in packages:
            vulns = await self._query_osv(pkg_name, pkg_version)
            if not vulns:
                vulns = await self._query_pypi(pkg_name, pkg_version)
            for v in vulns:
                vulnerabilities.append({
                    "package": pkg_name,
                    "version": pkg_version,
                    "vuln": v,
                })

        return self._format_scan_results(vulnerabilities, len(packages))

    async def _check_package(self, kwargs: dict[str, Any]) -> str:
        """특정 패키지의 취약점을 확인합니다."""
        package = kwargs.get("package", "").strip()
        version = kwargs.get("version", "latest").strip()

        if not package:
            return "package 파라미터가 필요합니다. 예: package='requests'"

        vulns = await self._query_osv(package, version)
        if not vulns:
            vulns = await self._query_pypi(package, version)

        if not vulns:
            return f"✅ {package} {version} — 알려진 취약점이 없습니다."

        lines = [f"## {package} {version} 취약점 ({len(vulns)}건)"]
        for v in vulns:
            emoji, level = self._severity_label(v)
            vuln_id = v.get("id", v.get("aliases", ["알 수 없음"])[0] if v.get("aliases") else "알 수 없음")
            summary = v.get("summary", v.get("details", "설명 없음"))[:200]
            fixed = ""
            for affected in v.get("affected", []):
                for r in affected.get("ranges", []):
                    for event in r.get("events", []):
                        if "fixed" in event:
                            fixed = event["fixed"]
            fix_text = f"\n   → 해결: pip install {package}>={fixed}" if fixed else ""
            lines.append(f"{emoji} [{level}] {vuln_id}: {summary}{fix_text}")

        return "\n".join(lines)

    async def _full_report(self, kwargs: dict[str, Any]) -> str:
        """전체 보안 보고서 (LLM 분석 포함)."""
        scan_result = await self._scan(kwargs)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 보안 전문가입니다.\n"
                "보안 스캔 결과를 분석하여 다음을 정리하세요:\n"
                "1. 전체 보안 상태 평가 (안전/주의/위험)\n"
                "2. 즉시 조치해야 할 취약점 (우선순위 순)\n"
                "3. 구체적인 해결 방법\n"
                "4. 장기적 보안 개선 권고\n"
                "한국어로, 비개발자도 이해할 수 있게 작성하세요."
            ),
            user_prompt=scan_result,
        )

        return f"{scan_result}\n\n---\n\n## 보안 분석\n\n{analysis}"

    # ── 결과 포맷팅 ──

    def _format_scan_results(self, vulnerabilities: list[dict], total_packages: int) -> str:
        vuln_count = len(vulnerabilities)
        safe_count = total_packages - len({v["package"] for v in vulnerabilities})

        lines = [
            "## 보안 스캔 결과",
            f"총 패키지: {total_packages}개 | 취약점 발견: {vuln_count}개 | 안전: {safe_count}개",
            "",
        ]

        if not vulnerabilities:
            lines.append("✅ 알려진 취약점이 발견되지 않았습니다.")
            return "\n".join(lines)

        for entry in vulnerabilities:
            pkg = entry["package"]
            ver = entry["version"]
            v = entry["vuln"]
            emoji, level = self._severity_label(v)
            vuln_id = v.get("id", v.get("aliases", ["알 수 없음"])[0] if v.get("aliases") else "알 수 없음")
            summary = v.get("summary", v.get("details", "설명 없음"))[:200]
            # 수정 버전 찾기
            fixed = ""
            for affected in v.get("affected", []):
                for r in affected.get("ranges", []):
                    for event in r.get("events", []):
                        if "fixed" in event:
                            fixed = event["fixed"]
            fix_text = f"\n   → 해결: pip install {pkg}>={fixed}" if fixed else ""
            lines.append(f"{emoji} [{level}] {pkg} {ver} — {vuln_id}: {summary}{fix_text}")

        return "\n".join(lines)

    @staticmethod
    def _format_pip_audit(audit_data: dict | list, total_packages: int) -> str:
        """pip-audit JSON 결과를 포맷팅합니다."""
        entries = audit_data if isinstance(audit_data, list) else audit_data.get("dependencies", [])
        vuln_entries = [e for e in entries if e.get("vulns")]
        vuln_count = sum(len(e.get("vulns", [])) for e in vuln_entries)

        lines = [
            "## 보안 스캔 결과 (pip-audit)",
            f"총 패키지: {total_packages}개 | 취약점 발견: {vuln_count}개",
            "",
        ]

        if not vuln_entries:
            lines.append("✅ 알려진 취약점이 발견되지 않았습니다.")
            return "\n".join(lines)

        for entry in vuln_entries:
            pkg = entry.get("name", "알 수 없음")
            ver = entry.get("version", "?")
            for v in entry.get("vulns", []):
                vid = v.get("id", "?")
                fix = v.get("fix_versions", [])
                desc = v.get("description", "설명 없음")[:200]
                fix_text = f"\n   → 해결: pip install {pkg}>={fix[0]}" if fix else ""
                lines.append(f"🔴 {pkg} {ver} — {vid}: {desc}{fix_text}")

        return "\n".join(lines)
