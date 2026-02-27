"""
영상 편집 도구 (ffmpeg).

립싱크 영상에 자막, BGM, 인트로/아웃트로를 합성합니다.
AI 인플루언서 영상 제작 파이프라인의 마지막 단계.

action: subtitle | bgm | concat | full
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from datetime import datetime
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.video_editor")

VIDEO_DIR = os.path.join(os.getcwd(), "output", "videos")


class VideoEditorTool(BaseTool):
    """ffmpeg 기반 영상 편집 도구."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "subtitle")
        if action == "subtitle":
            return await self._add_subtitle(kwargs)
        elif action == "bgm":
            return await self._add_bgm(kwargs)
        elif action == "concat":
            return await self._concat_clips(kwargs)
        elif action == "full":
            return await self._full_pipeline(kwargs)
        else:
            return (
                "## 사용 가능한 action\n"
                "- `subtitle`: 영상에 자막(SRT) 합성\n"
                "- `bgm`: 영상에 BGM 믹싱\n"
                "- `concat`: 여러 클립 이어붙이기\n"
                "- `full`: 전체 파이프라인 (자막+BGM)\n"
            )

    @staticmethod
    def _ensure_dir() -> str:
        os.makedirs(VIDEO_DIR, exist_ok=True)
        return VIDEO_DIR

    def _resolve_video(self, kwargs: dict) -> str | None:
        """영상 경로 결정."""
        video = kwargs.get("video", "")
        if video and os.path.isfile(video):
            return video
        if video:
            candidate = os.path.join(VIDEO_DIR, video)
            if os.path.isfile(candidate):
                return candidate
        # 가장 최신 립싱크 영상
        if os.path.isdir(VIDEO_DIR):
            mp4s = sorted(
                [f for f in os.listdir(VIDEO_DIR) if f.startswith("lipsync_") and f.endswith(".mp4")],
                reverse=True,
            )
            if mp4s:
                return os.path.join(VIDEO_DIR, mp4s[0])
        return None

    async def _run_ffmpeg(self, cmd: list[str]) -> tuple[bool, str]:
        """ffmpeg 명령 실행."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr
        except FileNotFoundError:
            return False, "ffmpeg이 설치되지 않았습니다. sudo apt install ffmpeg"
        except subprocess.TimeoutExpired:
            return False, "ffmpeg 실행 시간 초과 (5분)"
        except Exception as e:
            return False, str(e)

    async def _generate_srt(self, text: str, duration_hint: float = 0) -> str:
        """텍스트를 SRT 자막 파일로 변환."""
        out_dir = self._ensure_dir()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        srt_path = os.path.join(out_dir, f"sub_{ts}.srt")

        # 문장 단위로 분할
        sentences = [s.strip() for s in text.replace(".", ".\n").replace("!", "!\n").replace("?", "?\n").split("\n") if s.strip()]
        if not sentences:
            sentences = [text]

        # 균등 배분
        if duration_hint <= 0:
            duration_hint = len(text) / 4.0  # 한국어 초당 ~4자

        interval = duration_hint / max(len(sentences), 1)
        lines = []
        for i, sent in enumerate(sentences):
            start = i * interval
            end = (i + 1) * interval
            sh, sm, ss = int(start // 3600), int((start % 3600) // 60), start % 60
            eh, em, es = int(end // 3600), int((end % 3600) // 60), end % 60
            lines.append(f"{i + 1}")
            lines.append(f"{sh:02d}:{sm:02d}:{ss:06.3f} --> {eh:02d}:{em:02d}:{es:06.3f}".replace(".", ","))
            lines.append(sent)
            lines.append("")

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return srt_path

    async def _add_subtitle(self, kwargs: dict) -> str:
        """영상에 자막 합성."""
        video_path = self._resolve_video(kwargs)
        if not video_path:
            return "영상 파일을 찾을 수 없습니다."

        srt_path = kwargs.get("srt", "")
        text = kwargs.get("text", "")

        if not srt_path and text:
            srt_path = await self._generate_srt(text)
        elif srt_path and not os.path.isfile(srt_path):
            return f"SRT 파일을 찾을 수 없습니다: {srt_path}"
        elif not srt_path:
            return "자막 텍스트(text) 또는 SRT 파일 경로(srt)를 입력해주세요."

        out_dir = self._ensure_dir()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(out_dir, f"subtitled_{ts}.mp4")

        font_size = kwargs.get("font_size", 24)
        font_color = kwargs.get("font_color", "white")

        # ffmpeg 자막 필터 — 윈도우 경로 이스케이프
        srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
        vf = f"subtitles='{srt_escaped}':force_style='FontSize={font_size},PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Alignment=2'"

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", vf,
            "-c:a", "copy",
            output_file,
        ]

        ok, msg = await self._run_ffmpeg(cmd)
        if not ok:
            return f"자막 합성 실패: {msg}"

        filename = os.path.basename(output_file)
        return (
            f"## 자막 합성 완료\n\n"
            f"| 항목 | 값 |\n|------|----|\n"
            f"| 원본 | `{os.path.basename(video_path)}` |\n"
            f"| 자막 | `{os.path.basename(srt_path)}` |\n"
            f"| 폰트 크기 | {font_size} |\n\n"
            f"### 저장된 파일\n"
            f"- `output/videos/{filename}`"
        )

    async def _add_bgm(self, kwargs: dict) -> str:
        """영상에 BGM 믹싱."""
        video_path = self._resolve_video(kwargs)
        if not video_path:
            return "영상 파일을 찾을 수 없습니다."

        bgm_path = kwargs.get("bgm", "")
        if not bgm_path or not os.path.isfile(bgm_path):
            return "BGM 파일 경로(bgm)를 지정해주세요."

        bgm_volume = float(kwargs.get("bgm_volume", 0.15))

        out_dir = self._ensure_dir()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(out_dir, f"bgm_{ts}.mp4")

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", bgm_path,
            "-filter_complex",
            f"[1:a]volume={bgm_volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first[a]",
            "-map", "0:v",
            "-map", "[a]",
            "-c:v", "copy",
            "-c:a", "aac",
            output_file,
        ]

        ok, msg = await self._run_ffmpeg(cmd)
        if not ok:
            return f"BGM 믹싱 실패: {msg}"

        filename = os.path.basename(output_file)
        return (
            f"## BGM 믹싱 완료\n\n"
            f"| 항목 | 값 |\n|------|----|\n"
            f"| 원본 | `{os.path.basename(video_path)}` |\n"
            f"| BGM | `{os.path.basename(bgm_path)}` |\n"
            f"| BGM 볼륨 | {bgm_volume} |\n\n"
            f"### 저장된 파일\n"
            f"- `output/videos/{filename}`"
        )

    async def _concat_clips(self, kwargs: dict) -> str:
        """여러 클립 이어붙이기."""
        clips = kwargs.get("clips", [])
        if not clips or not isinstance(clips, list) or len(clips) < 2:
            return "이어붙일 클립 목록(clips)을 리스트로 입력해주세요. 최소 2개 필요."

        # 경로 확인
        valid_clips = []
        for c in clips:
            if os.path.isfile(c):
                valid_clips.append(c)
            elif os.path.isfile(os.path.join(VIDEO_DIR, c)):
                valid_clips.append(os.path.join(VIDEO_DIR, c))

        if len(valid_clips) < 2:
            return f"유효한 클립이 2개 미만입니다. 확인된 파일: {len(valid_clips)}개"

        out_dir = self._ensure_dir()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # concat list 파일 생성
        list_file = os.path.join(out_dir, f"concat_{ts}.txt")
        with open(list_file, "w") as f:
            for c in valid_clips:
                f.write(f"file '{c}'\n")

        output_file = os.path.join(out_dir, f"concat_{ts}.mp4")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            output_file,
        ]

        ok, msg = await self._run_ffmpeg(cmd)
        # 임시 파일 삭제
        if os.path.exists(list_file):
            os.remove(list_file)

        if not ok:
            return f"클립 합치기 실패: {msg}"

        filename = os.path.basename(output_file)
        return (
            f"## 클립 합치기 완료\n\n"
            f"| 항목 | 값 |\n|------|----|\n"
            f"| 클립 수 | {len(valid_clips)}개 |\n\n"
            f"### 저장된 파일\n"
            f"- `output/videos/{filename}`"
        )

    async def _full_pipeline(self, kwargs: dict) -> str:
        """전체 편집 파이프라인: 자막 + BGM."""
        results = []

        # 자막이 있으면 먼저 합성
        if kwargs.get("text") or kwargs.get("srt"):
            sub_result = await self._add_subtitle(kwargs)
            results.append(sub_result)
            if "실패" in sub_result:
                return sub_result

        # BGM이 있으면 합성
        if kwargs.get("bgm"):
            bgm_result = await self._add_bgm(kwargs)
            results.append(bgm_result)

        if not results:
            return "text/srt(자막) 또는 bgm(배경음악) 중 하나 이상을 지정해주세요."

        return "\n\n---\n\n".join(results)
