---
name: defuddle
description: Defuddle CLI를 사용하여 웹 페이지에서 깨끗한 마크다운 콘텐츠를 추출하며, 불필요한 요소와 네비게이션을 제거하여 토큰을 절약합니다. 사용자가 읽거나 분석할 URL을 제공할 때, 온라인 문서, 기사, 블로그 포스트 또는 일반 웹 페이지에 WebFetch 대신 사용합니다.
---

# Defuddle

Defuddle CLI를 사용하여 웹 페이지에서 깨끗하고 읽기 쉬운 콘텐츠를 추출합니다. 일반 웹 페이지에는 WebFetch보다 우선 사용합니다 — 네비게이션, 광고, 불필요한 요소를 제거하여 토큰 사용량을 줄입니다.

설치되지 않은 경우: `npm install -g defuddle-cli`

## 사용법

항상 마크다운 출력을 위해 `--md`를 사용합니다:

```bash
defuddle parse <url> --md
```

파일로 저장:

```bash
defuddle parse <url> --md -o content.md
```

특정 메타데이터 추출:

```bash
defuddle parse <url> -p title
defuddle parse <url> -p description
defuddle parse <url> -p domain
```

## 출력 형식

| 플래그 | 형식 |
|------|--------|
| `--md` | 마크다운 (기본 선택) |
| `--json` | HTML과 마크다운이 모두 포함된 JSON |
| (없음) | HTML |
| `-p <name>` | 특정 메타데이터 속성 |
