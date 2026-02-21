# 나노바나나 Pro 이미지 + Veo 3.1 영상 생성 실제 구현

- **날짜**: 2026-02-22
- **빌드**: #459
- **브랜치**: claude/gemini-media-generation

## 변경 내용

### 1. 나노바나나 Pro 이미지 생성기 전면 개편
- **이전**: `gemini_image_generator.py`가 LLM 호출로 "프롬프트만" 생성 (663줄)
- **이후**: `gemini-3-pro-image-preview` API로 **실제 이미지** 직접 생성
- 교수급 디자인 지식(플랫폼 사양, 5가지 스타일 가이드, 색상 심리학)이 프롬프트에 자동 반영
- 4K 해상도, 10종 aspect ratio(1:1, 16:9, 9:16 등), 9가지 action 지원
- `GOOGLE_API_KEY` 하나로 동작 (별도 키 불필요)

### 2. Veo 3.1 영상 생성 도구 신규 생성
- `gemini_video_generator.py` 신규 파일
- `veo-3.1-generate-preview` 모델로 실제 영상 생성
- action: generate(직접), reels(9:16 세로), ad(16:9 가로)
- 720p/1080p/4K, 4~8초, 음성 자동 생성
- 릴스/쇼츠 전용 세로 영상 자동 최적화

### 3. 미디어 서빙 엔드포인트
- `/api/media/images/{filename}` — 이미지 파일 서빙
- `/api/media/videos/{filename}` — 영상 파일 서빙
- `/api/media/list` — 생성된 미디어 목록 API

### 4. COMM STATION UI 개선
- **미디어 갤러리 탭** 추가 (이미지/영상 썸네일 그리드)
- **승인 대기열** 이미지/영상 인라인 미리보기 추가
- 이미지 클릭 → 원본 크기 새 탭으로 열기
- 영상 → 인라인 재생 컨트롤

### 5. 에이전트 도구 연결
- content_specialist: `image_generator`(DALL-E) → `gemini_image_generator` + `gemini_video_generator`
- tools.yaml, pool.py, agents.yaml 동기화 완료

## 수정 파일 (9개)
| 파일 | 변경 |
|------|------|
| `src/tools/gemini_image_generator.py` | 전면 개편 (프롬프트→실제 생성) |
| `src/tools/gemini_video_generator.py` | **신규** (Veo 3.1) |
| `web/mini_server.py` | 미디어 서빙 3개 엔드포인트 추가 |
| `web/templates/index.html` | 미디어 갤러리 + 미리보기 UI |
| `config/tools.yaml` | 두 도구 스키마 업데이트 |
| `config/agents.yaml` | content_specialist 도구 교체 |
| `src/tools/pool.py` | 비디오 생성기 매핑 추가 |
| `config/agents.json` | yaml2json 자동 생성 |
| `config/tools.json` | yaml2json 자동 생성 |

## 발견한 버그
없음

## 비용 참고
- 나노바나나 Pro 이미지: 유료 API (GOOGLE_API_KEY 사용)
- Veo 3.1 영상: ~$0.10~0.40/초 (8초 = ~$0.80~$3.20)
