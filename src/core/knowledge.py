"""
Knowledge Manager: 에이전트별/본부별 지식 관리 시스템.

knowledge/ 폴더의 마크다운 파일을 읽어
에이전트의 system_prompt에 자동으로 주입합니다.

구조:
  knowledge/
  ├── global/          ← 전 에이전트 공유 지식
  │   └── company_rules.md
  ├── leet_master/     ← LEET MASTER 본부 공유 지식
  │   └── product_info.md
  └── finance/         ← 금융분석 본부 공유 지식
      └── investment_policy.md
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("corthex.knowledge")


class KnowledgeManager:
    """Loads and injects knowledge into agent system prompts."""

    def __init__(self, knowledge_dir: Path) -> None:
        self.knowledge_dir = knowledge_dir
        self._cache: dict[str, str] = {}

    def load_all(self) -> None:
        """Load all knowledge files into cache."""
        self._cache.clear()
        if not self.knowledge_dir.exists():
            logger.warning("knowledge 디렉토리 없음: %s", self.knowledge_dir)
            return

        count = 0
        for md_file in self.knowledge_dir.rglob("*.md"):
            rel_path = md_file.relative_to(self.knowledge_dir)
            key = str(rel_path.parent)  # e.g., "global", "leet_master", "finance"
            content = md_file.read_text(encoding="utf-8").strip()
            if content:
                if key not in self._cache:
                    self._cache[key] = ""
                self._cache[key] += f"\n\n{content}"
                count += 1

        logger.info("지식 파일 %d개 로드 완료", count)

    def get_knowledge_for_agent(self, division: str) -> str:
        """Get combined knowledge for a specific agent's division."""
        parts: list[str] = []

        # 1. Global knowledge (모든 에이전트 공통)
        if "global" in self._cache:
            parts.append(self._cache["global"])

        # 2. Division-specific knowledge
        #    division can be "leet_master.tech", "finance.investment", etc.
        #    We check each level: "leet_master.tech" -> "leet_master", "finance.investment" -> "finance"
        if division:
            # Top-level division
            top_div = division.split(".")[0]
            if top_div in self._cache:
                parts.append(self._cache[top_div])

            # Exact division
            if division in self._cache and division != top_div:
                parts.append(self._cache[division])

        if not parts:
            return ""

        return "\n\n---\n[공유 지식]\n" + "\n".join(parts)

    # ─── CRUD Operations ───

    def list_files(self) -> list[dict]:
        """List all knowledge files with metadata."""
        if not self.knowledge_dir.exists():
            return []
        files = []
        for md_file in sorted(self.knowledge_dir.rglob("*.md")):
            rel = md_file.relative_to(self.knowledge_dir)
            files.append({
                "folder": str(rel.parent),
                "filename": rel.name,
                "path": str(rel),
                "size": md_file.stat().st_size,
            })
        return files

    def read_file(self, rel_path: str) -> str | None:
        """Read a single knowledge file by relative path."""
        fp = self.knowledge_dir / rel_path
        if not fp.exists() or not fp.is_file():
            return None
        return fp.read_text(encoding="utf-8")

    def save_file(self, folder: str, filename: str, content: str) -> str:
        """Save (create/update) a knowledge file. Returns the relative path."""
        if not filename.endswith(".md"):
            filename += ".md"
        target_dir = self.knowledge_dir / folder
        target_dir.mkdir(parents=True, exist_ok=True)
        fp = target_dir / filename
        fp.write_text(content, encoding="utf-8")
        self.load_all()  # reload cache
        rel = str(fp.relative_to(self.knowledge_dir))
        logger.info("지식 파일 저장: %s", rel)
        return rel

    def delete_file(self, rel_path: str) -> bool:
        """Delete a knowledge file. Returns True on success."""
        fp = self.knowledge_dir / rel_path
        if not fp.exists():
            return False
        fp.unlink()
        self.load_all()  # reload cache
        logger.info("지식 파일 삭제: %s", rel_path)
        return True
