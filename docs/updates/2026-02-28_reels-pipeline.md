# 릴스 자동 발행 파이프라인 — URL 정규화 + output 경로 통일

**빌드**: #675 | **날짜**: 2026-02-28

## 요약

Instagram 릴스 자동 발행을 위한 URL 정규화 파이프라인 구현 + 전체 미디어 도구의 output 경로 버그 수정.

## 변경

| 파일 | 변경 |
|------|------|
| `src/tools/sns/instagram_publisher.py` | `_resolve_media_url()` 추가 — 상대 경로를 절대 URL로 변환 |
| `src/tools/gemini_video_generator.py` | 퍼블릭 URL 반환 + 경로 수정 |
| `src/tools/lipsync_video_generator.py` | 퍼블릭 URL 반환 + 경로 수정 |
| `web/handlers/media_handler.py` | `os.getcwd()` → `Path(__file__)` 기반 절대경로 |
| `src/tools/gemini_image_generator.py` | 경로 수정 |
| `src/tools/image_generator.py` | 경로 수정 |
| `src/tools/tts_generator.py` | 경로 수정 |
| `src/tools/chart_generator.py` | 경로 수정 |
| `src/tools/audio_transcriber.py` | 경로 수정 |
| `src/tools/video_editor.py` | 경로 수정 |
| `config/agents.json` | CMO Instagram 활성화 + reasoning_effort 조정 |
| `.gitignore` | output 미디어 파일 무시 + .gitkeep 유지 |

## 핵심 수정

### 1. URL 정규화 (`_resolve_media_url`)

Instagram Graph API는 퍼블릭 URL만 허용. 영상 생성기가 반환하는 상대 경로를 자동 변환:

```
/api/media/videos/file.mp4 → https://corthex-hq.com/api/media/videos/file.mp4
output/videos/file.mp4     → https://corthex-hq.com/api/media/videos/file.mp4
file.mp4                   → https://corthex-hq.com/api/media/videos/file.mp4
```

### 2. output 경로 통일 (버그 수정)

**문제**: 서버가 `/home/ubuntu/CORTHEX_HQ/web`에서 실행 → `os.getcwd()` 기반 도구들이 `web/output/`에 파일 저장 → `app.py`의 `/output` 정적 마운트는 프로젝트 루트 `output/`을 가리킴 → 경로 불일치.

**수정**: 전체 미디어 도구 8개의 OUTPUT_DIR을 `__file__` 기반 절대경로로 통일.

### 3. nginx 경로 발견

nginx가 `/api/`와 `/ws`만 FastAPI로 프록시. `/output/` 정적 경로는 nginx를 통과하지 못함. → Instagram URL을 `/api/media/videos/` 경로로 설정 (정상 동작 확인).

## 릴스 발행 전체 플로우

```
1. 에이전트: "릴스 만들어서 인스타에 올려줘"
2. Veo 3.1 또는 립싱크로 영상 생성 → /home/ubuntu/CORTHEX_HQ/output/videos/
3. 생성기가 퍼블릭 URL 반환: https://corthex-hq.com/api/media/videos/파일명.mp4
4. CMO가 sns_manager(action=submit, platform=instagram, media_urls=[URL], extra={media_type: REELS})
5. CEO 승인 대기 → 승인 후 CMO가 publish
6. instagram_publisher._resolve_media_url() → 절대 URL 변환
7. Instagram Graph API: POST /media (video_url) → wait → POST /media_publish
8. 발행 완료 URL 반환
```
