# image_generator — 이미지 생성기 도구 가이드

## 이 도구는 뭔가요?
AI로 이미지를 만들어주는 도구입니다.
텍스트로 "이런 이미지를 만들어줘"라고 설명하면, DALL-E 3(OpenAI의 이미지 생성 AI)가 그에 맞는 이미지를 자동으로 그려줍니다.
새 이미지를 만드는 것뿐 아니라, 기존 이미지를 편집하거나 비슷한 스타일의 변형을 만드는 것도 가능합니다.

## 어떤 API를 쓰나요?
- **OpenAI DALL-E 3** — 새 이미지 생성 (고품질)
- **OpenAI DALL-E 2** — 이미지 편집, 변형 생성
- 비용: **유료**
  - DALL-E 3 standard: **$0.040/장** (약 55원)
  - DALL-E 3 HD: **$0.080/장** (약 110원)
  - DALL-E 2 편집/변형: **$0.020/장** (약 27원)
- 필요한 키: `OPENAI_API_KEY`

## 사용법

### action=generate (새 이미지 생성)
```
action=generate, prompt="이미지 설명", size="1024x1024", quality="standard", style="vivid", n=1
```
- 텍스트 설명(프롬프트)을 기반으로 새 이미지를 생성합니다
- prompt: 원하는 이미지를 상세히 설명 (필수, 영어 권장)
- size: "1024x1024" (정사각형, 기본값), "1024x1792" (세로), "1792x1024" (가로)
- quality: "standard" (기본, $0.040) 또는 "hd" (고해상도, $0.080)
- style: "vivid" (선명, 기본값) 또는 "natural" (자연스러운)
- n: 생성할 이미지 수 (기본값: 1)
- 반환: 프롬프트, 크기, 품질, 예상 비용, 저장된 파일 경로

**예시:**
- `action=generate, prompt="A modern Korean startup office with large windows, minimalist design, warm lighting"` → 스타트업 사무실 이미지 생성

### action=edit (기존 이미지 편집)
```
action=edit, image_path="/path/to/image.png", prompt="편집 내용 설명"
```
- 기존 이미지를 AI가 프롬프트에 맞게 편집합니다 (DALL-E 2 사용)
- image_path: 원본 이미지 파일 경로 (필수)
- prompt: 어떻게 편집할지 설명 (필수)

### action=variation (이미지 변형 생성)
```
action=variation, image_path="/path/to/image.png", n=3
```
- 기존 이미지와 비슷한 스타일의 변형(바리에이션)을 만들어줍니다 (DALL-E 2 사용)
- n: 만들 변형 수 (기본값: 1)

## 이 도구를 쓰는 에이전트들

### 1. 프론트엔드 Specialist (frontend_specialist)
**언제 쓰나?** UI 목업(시안) 이미지, 아이콘, 배경 이미지 등 디자인 에셋(소재) 제작
**어떻게 쓰나?**
- generate로 웹사이트/앱 디자인에 필요한 이미지 소재 생성
- variation으로 여러 디자인 시안을 만들어 CEO에게 선택지 제공

**실전 시나리오:**
> CEO가 "CORTHEX HQ 대시보드에 멋진 배경 이미지 넣어줘" 라고 하면:
> 1. `action=generate, prompt="Abstract futuristic dashboard background, dark theme"` 로 배경 생성
> 2. `action=variation, n=3`으로 3가지 변형 생성
> 3. CEO에게 4개 시안을 보여주고 선택

### 2. 콘텐츠 Specialist (content_specialist)
**언제 쓰나?** SNS 포스트용 이미지, 블로그 썸네일(미리보기 이미지), 뉴스레터 삽화
**어떻게 쓰나?**
- generate로 콘텐츠에 맞는 이미지 제작
- edit로 기존 이미지에 텍스트/배경 추가

**실전 시나리오:**
> CEO가 "이번 주 뉴스레터에 AI 시장 관련 이미지 넣어줘" 라고 하면:
> 1. `action=generate, prompt="Clean illustration of AI technology growth, professional business style", quality="hd"` 생성
> 2. 뉴스레터에 삽입

## 주의사항
- DALL-E 3은 이미지 1장당 $0.040~$0.080 비용이 발생합니다 (많이 생성하면 비용 주의)
- 프롬프트는 **영어**로 작성하는 것이 품질이 더 좋습니다
- DALL-E 3이 프롬프트를 자동으로 수정(확장)할 수 있습니다 (revised_prompt로 확인 가능)
- edit와 variation은 DALL-E 2를 사용하므로 DALL-E 3보다 품질이 낮을 수 있습니다
- 생성된 이미지는 `output/images/` 디렉토리에 PNG 파일로 저장됩니다
- 사람 얼굴, 유명인, 브랜드 로고 등은 OpenAI 정책에 의해 생성이 거부될 수 있습니다
