"""음성 변환기 도구 — Whisper API로 음성→텍스트 변환."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.audio_transcriber")

# 프로젝트 루트의 output/transcripts/ (os.getcwd() 의존 제거)
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "output", "transcripts")

# Whisper API 최대 파일 크기: 25MB
MAX_FILE_SIZE = 25 * 1024 * 1024


def _get_openai():
    try:
        import openai
        return openai
    except ImportError:
        return None


def _get_pydub():
    try:
        from pydub import AudioSegment
        return AudioSegment
    except ImportError:
        return None


class AudioTranscriberTool(BaseTool):
    """음성/오디오를 텍스트로 변환하는 도구 (OpenAI Whisper API)."""

    SUPPORTED_FORMATS = {"mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm", "ogg", "flac"}

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "transcribe")
        if action == "transcribe":
            return await self._transcribe(kwargs)
        elif action == "translate":
            return await self._translate(kwargs)
        elif action == "summary":
            return await self._summary(kwargs)
        elif action == "meeting":
            return await self._meeting(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능한 action: transcribe(텍스트 변환), translate(영어 번역), "
                "summary(요약), meeting(회의록 변환)"
            )

    @staticmethod
    def _get_api_key() -> str:
        return os.getenv("OPENAI_API_KEY", "")

    @staticmethod
    def _key_msg() -> str:
        return "OPENAI_API_KEY 환경변수가 설정되지 않았습니다."

    def _check_file(self, file_path: str) -> str | None:
        if not file_path:
            return "오디오 파일 경로(file_path)를 입력해주세요."
        if not os.path.isfile(file_path):
            return f"파일을 찾을 수 없습니다: {file_path}"
        ext = file_path.lower().rsplit(".", 1)[-1] if "." in file_path else ""
        if ext not in self.SUPPORTED_FORMATS:
            supported = ", ".join(sorted(self.SUPPORTED_FORMATS))
            return f"지원하지 않는 형식: .{ext} (지원: {supported})"
        return None

    async def _transcribe_file(self, file_path: str, language: str = "ko") -> str:
        """단일 파일 트랜스크립션."""
        openai = _get_openai()
        if openai is None:
            return "openai 라이브러리가 설치되지 않았습니다. pip install openai"

        api_key = self._get_api_key()
        if not api_key:
            return self._key_msg()

        file_size = os.path.getsize(file_path)

        # 25MB 초과 시 분할
        if file_size > MAX_FILE_SIZE:
            return await self._transcribe_large_file(file_path, language)

        try:
            client = openai.OpenAI(api_key=api_key)
            with open(file_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language,
                    response_format="text",
                )
            return transcript
        except Exception as e:
            logger.error("트랜스크립션 실패: %s", e)
            return f"트랜스크립션 실패: {e}"

    async def _transcribe_large_file(self, file_path: str, language: str) -> str:
        """대용량 오디오 파일 분할 처리."""
        AudioSegment = _get_pydub()
        if AudioSegment is None:
            return (
                f"파일 크기가 25MB를 초과합니다 ({os.path.getsize(file_path) / 1024 / 1024:.1f}MB).\n"
                "pydub 라이브러리가 있으면 자동 분할 가능합니다. pip install pydub"
            )

        try:
            audio = AudioSegment.from_file(file_path)
            chunk_length_ms = 5 * 60 * 1000  # 5분 단위
            chunks = [audio[i:i + chunk_length_ms] for i in range(0, len(audio), chunk_length_ms)]

            openai = _get_openai()
            client = openai.OpenAI(api_key=self._get_api_key())
            transcripts: list[str] = []

            for i, chunk in enumerate(chunks):
                # 임시 파일로 저장
                temp_path = f"/tmp/audio_chunk_{i}.mp3"
                chunk.export(temp_path, format="mp3")

                with open(temp_path, "rb") as f:
                    result = client.audio.transcriptions.create(
                        model="whisper-1", file=f, language=language, response_format="text",
                    )
                transcripts.append(result)
                os.remove(temp_path)

            return "\n\n".join(transcripts)
        except Exception as e:
            return f"대용량 파일 분할 처리 실패: {e}"

    async def _transcribe(self, kwargs: dict) -> str:
        """음성 → 텍스트 변환."""
        file_path = kwargs.get("file_path", "")
        language = kwargs.get("language", "ko")

        err = self._check_file(file_path)
        if err:
            return err

        text = await self._transcribe_file(file_path, language)

        # 결과 저장
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(OUTPUT_DIR, f"transcript_{ts}.txt")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)

        file_size = os.path.getsize(file_path)
        logger.info("트랜스크립션 완료: %s → %s", file_path, output_path)

        return (
            f"## 음성 → 텍스트 변환 완료\n\n"
            f"| 항목 | 값 |\n|------|----|\n"
            f"| 원본 파일 | {file_path} |\n"
            f"| 파일 크기 | {file_size / 1024 / 1024:.1f}MB |\n"
            f"| 언어 | {language} |\n"
            f"| 텍스트 길이 | {len(text):,}자 |\n"
            f"| 저장 경로 | {output_path} |\n\n"
            f"### 변환 결과\n\n{text[:3000]}{'...' if len(text) > 3000 else ''}"
        )

    async def _translate(self, kwargs: dict) -> str:
        """음성 → 영어 텍스트 변환."""
        file_path = kwargs.get("file_path", "")
        err = self._check_file(file_path)
        if err:
            return err

        openai = _get_openai()
        if openai is None:
            return "openai 라이브러리가 설치되지 않았습니다."

        api_key = self._get_api_key()
        if not api_key:
            return self._key_msg()

        try:
            client = openai.OpenAI(api_key=api_key)
            with open(file_path, "rb") as audio_file:
                translation = client.audio.translations.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text",
                )
            return (
                f"## 음성 → 영어 번역 완료\n\n"
                f"- 원본 파일: {file_path}\n\n"
                f"### 번역 결과\n\n{translation}"
            )
        except Exception as e:
            return f"번역 실패: {e}"

    async def _summary(self, kwargs: dict) -> str:
        """음성 → 텍스트 → 요약."""
        file_path = kwargs.get("file_path", "")
        language = kwargs.get("language", "ko")

        err = self._check_file(file_path)
        if err:
            return err

        text = await self._transcribe_file(file_path, language)
        if "실패" in text or "설치" in text:
            return text

        summary = await self._llm_call(
            system_prompt=(
                "당신은 음성 녹음 요약 전문가입니다. "
                "음성에서 변환된 텍스트를 읽고 핵심 내용을 한국어로 구조적으로 요약하세요.\n"
                "1. 전체 주제\n2. 핵심 내용 (5줄 이내)\n3. 주요 키워드\n4. 특이사항"
            ),
            user_prompt=text[:8000],
        )

        return (
            f"## 음성 요약\n\n- 원본: {file_path}\n- 텍스트 길이: {len(text):,}자\n\n"
            f"### 요약\n\n{summary}"
        )

    async def _meeting(self, kwargs: dict) -> str:
        """회의 녹음 → 회의록 자동 생성."""
        file_path = kwargs.get("file_path", "")
        language = kwargs.get("language", "ko")
        meeting_title = kwargs.get("title", "회의")
        participants = kwargs.get("participants", "")

        err = self._check_file(file_path)
        if err:
            return err

        text = await self._transcribe_file(file_path, language)
        if "실패" in text or "설치" in text:
            return text

        meeting_notes = await self._llm_call(
            system_prompt=(
                "당신은 회의록 작성 전문가입니다. "
                "회의 녹음에서 변환된 텍스트를 읽고 공식 회의록을 작성하세요.\n\n"
                "회의록 형식:\n"
                "1. **회의 정보** (제목, 참석자, 날짜)\n"
                "2. **안건 목록** (논의된 주제들)\n"
                "3. **논의 내용** (안건별 상세)\n"
                "4. **결정 사항** (합의된 내용)\n"
                "5. **실행 항목** (누가, 무엇을, 언제까지)\n"
                "6. **다음 회의** (있으면)"
            ),
            user_prompt=(
                f"회의 제목: {meeting_title}\n"
                f"참석자: {participants}\n"
                f"날짜: {datetime.now().strftime('%Y-%m-%d')}\n\n"
                f"녹음 내용:\n{text[:8000]}"
            ),
        )

        # 회의록 저장
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(OUTPUT_DIR, f"meeting_{ts}.md")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(meeting_notes)

        return (
            f"## 회의록 생성 완료\n\n"
            f"- 원본 녹음: {file_path}\n"
            f"- 회의록 저장: {output_path}\n\n"
            f"---\n\n{meeting_notes}"
        )
