# audio_transcriber — 음성 변환기 도구 가이드

## 이 도구는 뭔가요?
음성/오디오 파일을 텍스트로 자동 변환해주는 도구입니다.
회의 녹음, 인터뷰, 강연 등의 음성 파일을 넣으면 AI(OpenAI Whisper)가 말한 내용을 텍스트로 받아적어줍니다.
한국어 음성을 영어로 번역하거나, 녹음 내용을 자동 요약하거나, 회의록을 자동으로 작성하는 기능도 있습니다.

## 어떤 API를 쓰나요?
- **OpenAI Whisper API** (모델: `whisper-1`) — 음성인식(STT, Speech-to-Text)
- 비용: **유료** ($0.006/분, 약 8원/분 — 1시간 녹음 = 약 $0.36 = 약 500원)
- 필요한 키: `OPENAI_API_KEY`
- 지원 파일 형식: mp3, mp4, mpeg, mpga, m4a, wav, webm, ogg, flac
- 최대 파일 크기: 25MB (초과 시 자동 분할 처리)

## 사용법

### action=transcribe (음성 → 텍스트 변환)
```
action=transcribe, file_path="/path/to/audio.mp3", language="ko"
```
- 음성 파일을 텍스트로 변환합니다
- file_path: 오디오 파일 경로 (필수)
- language: 음성 언어 코드 — "ko" (한국어, 기본값), "en" (영어), "ja" (일본어) 등
- 반환: 원본 파일 정보, 파일 크기, 텍스트 길이, 변환된 텍스트, 저장 경로

**예시:**
- `action=transcribe, file_path="/home/ubuntu/recordings/meeting_0219.mp3"` → 한국어 회의 녹음을 텍스트로 변환

### action=translate (음성 → 영어 텍스트 변환)
```
action=translate, file_path="/path/to/audio.mp3"
```
- 어떤 언어의 음성이든 영어 텍스트로 번역합니다

**예시:**
- `action=translate, file_path="/home/ubuntu/recordings/korean_speech.mp3"` → 한국어 발표를 영어 텍스트로 번역

### action=summary (음성 → 텍스트 → 요약)
```
action=summary, file_path="/path/to/audio.mp3", language="ko"
```
- 음성을 텍스트로 변환한 뒤, AI가 핵심 내용을 자동 요약합니다
- 요약 항목: 전체 주제, 핵심 내용(5줄), 주요 키워드, 특이사항

**예시:**
- `action=summary, file_path="/home/ubuntu/recordings/ceo_briefing.mp3"` → CEO 브리핑 녹음의 핵심 요약

### action=meeting (회의 녹음 → 회의록 자동 생성)
```
action=meeting, file_path="/path/to/meeting.mp3", title="투자위원회", participants="CEO, CIO, CSO", language="ko"
```
- 회의 녹음을 텍스트로 변환한 뒤, AI가 공식 회의록 형식으로 정리합니다
- title: 회의 제목 (기본값: "회의")
- participants: 참석자 (선택)
- 회의록 형식: 회의 정보 → 안건 목록 → 논의 내용 → 결정 사항 → 실행 항목 → 다음 회의
- 반환: 회의록 텍스트 + 마크다운 파일로 자동 저장

**예시:**
- `action=meeting, file_path="/home/ubuntu/recordings/investment_meeting.mp3", title="2월 투자위원회", participants="CEO, CIO, 리스크관리 Specialist"` → 정형화된 회의록 생성

## 이 도구를 쓰는 에이전트들

현재 agents.yaml의 allowed_tools에 audio_transcriber가 직접 배정된 에이전트는 없습니다.
하지만 다음과 같은 에이전트들이 이 도구의 출력 결과를 간접적으로 활용할 수 있습니다:

### 활용 가능한 에이전트
- **비서실장 (chief_of_staff)**: CEO 회의 녹음을 회의록으로 변환하여 보고
- **출판/기록처장 (CPO)**: 회의/인터뷰 녹음을 텍스트로 변환하여 아카이빙
- **콘텐츠편집 Specialist**: 인터뷰/팟캐스트 녹음을 텍스트로 변환하여 콘텐츠 제작

**실전 시나리오:**
> CEO가 "오늘 회의 녹음 파일 회의록으로 만들어줘" 라고 하면:
> 1. `action=meeting, file_path="녹음파일경로", title="오늘 회의", participants="참석자목록"`
> 2. AI가 자동으로 안건, 논의 내용, 결정 사항, 실행 항목을 정리
> 3. 마크다운 회의록 파일이 output/transcripts/ 에 자동 저장

## 주의사항
- Whisper API 최대 파일 크기는 25MB입니다. 초과 시 pydub 라이브러리가 있으면 5분 단위로 자동 분할됩니다
- pydub 없이 25MB 초과 파일을 처리하면 에러가 발생합니다
- 음성 품질이 나쁘면(배경 소음, 먼 마이크) 변환 정확도가 떨어집니다
- summary와 meeting 액션은 Whisper API + AI 요약/정리 호출이 모두 발생하므로 비용이 더 듭니다
- 변환 결과는 output/transcripts/ 디렉토리에 자동 저장됩니다
- language 파라미터를 정확히 지정하면 인식 정확도가 올라갑니다
