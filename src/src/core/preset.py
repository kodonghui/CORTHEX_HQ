"""
Command Preset (Favorites) Manager for CORTHEX HQ.

CEO can save frequently used commands as presets and execute them by name.
Presets are stored in config/presets.yaml for persistence.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("corthex.preset")


class PresetManager:
    """Manages command presets stored in a YAML file."""

    def __init__(self, preset_path: Path) -> None:
        self._path = preset_path
        self._presets: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        """Load presets from YAML file."""
        if self._path.exists():
            try:
                raw = yaml.safe_load(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and "presets" in raw:
                    for item in raw["presets"]:
                        name = item.get("name", "")
                        command = item.get("command", "")
                        if name and command:
                            self._presets[name] = command
                logger.info("프리셋 %d개 로드: %s", len(self._presets), self._path)
            except Exception as e:
                logger.warning("프리셋 로드 실패: %s", e)

    def _save(self) -> None:
        """Save presets to YAML file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "presets": [
                {"name": name, "command": command}
                for name, command in self._presets.items()
            ]
        }
        self._path.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    def add(self, name: str, command: str) -> None:
        """Add or overwrite a preset."""
        self._presets[name] = command
        self._save()
        logger.info("프리셋 저장: '%s' → '%s'", name, command[:50])

    def remove(self, name: str) -> bool:
        """Remove a preset. Returns True if it existed."""
        if name in self._presets:
            del self._presets[name]
            self._save()
            return True
        return False

    def get(self, name: str) -> Optional[str]:
        """Get command for a preset name."""
        return self._presets.get(name)

    def list_all(self) -> dict[str, str]:
        """Return all presets as {name: command}."""
        return dict(self._presets)

    def resolve(self, user_input: str) -> Optional[str]:
        """If user_input matches a preset name, return the command. Else None."""
        return self._presets.get(user_input.strip())

    def to_list(self) -> list[dict[str, str]]:
        """Return presets as a list of dicts for API response."""
        return [
            {"name": name, "command": command}
            for name, command in self._presets.items()
        ]
