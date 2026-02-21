# CPO(출판/콘텐츠/기록 관리) 부서 API 및 도구 조사 보고서

**작성일**: 2026년 2월 13일
**작성자**: Claude AI
**목적**: 출판/콘텐츠/기록 관리 부서에서 실제로 사용 가능한 최신 API와 도구 조사

---

## 📋 목차

1. [노션(Notion) API](#1-notion-api)
2. [블로그/CMS 플랫폼 API](#2-블로그cms-플랫폼-api)
3. [이미지 생성 API](#3-이미지-생성-api)
4. [문서 변환 도구](#4-문서-변환-도구)
5. [프로젝트 기록/변경 로그 자동화](#5-프로젝트-기록변경-로그-자동화)
6. [종합 요약 및 추천](#6-종합-요약-및-추천)

---

## 1. Notion API

### 📖 개요
노션 API v1은 노션 페이지와 데이터베이스를 다른 도구와 연결해서 자동으로 작업할 수 있게 해주는 도구입니다.

### 🎯 주요 기능
- **페이지 생성**: 프로그램으로 노션 페이지를 자동으로 만들 수 있습니다
- **데이터베이스 관리**: 노션 데이터베이스에 데이터를 추가하거나 수정할 수 있습니다
- **실시간 업데이트**: 웹훅(Webhook, 알림 기능)으로 내용이 바뀔 때마다 알림을 받을 수 있습니다
- **AI 도구 연결**: ChatGPT, Claude 같은 AI 도구와 연결 가능합니다

### 💰 가격 (2026년 기준)
| 플랜 | 가격 | API 사용 | 특징 |
|------|------|----------|------|
| **Free** (무료) | $0 | ✅ 가능 | 무제한 페이지, 10명 게스트 공유 |
| **Plus** | $10/월 | ✅ 가능 | 7일 히스토리 |
| **Business** | $20/월 | ✅ 가능 | AI 기능 전체 이용 |
| **Enterprise** | 맞춤 가격 | ✅ 가능 | 대기업용 |

> ⚠️ **중요**: 모든 플랜에서 API를 무료로 사용할 수 있습니다!
> API 속도 제한: 초당 3회 요청 (15분당 2,700회)

### 🐍 Python 라이브러리: notion-client

**설치 방법**:
```bash
pip install notion-client
```

**사용 예시**:
```python
import os
from notion_client import Client

# 노션 연결 (토큰 필요)
notion = Client(auth=os.environ["NOTION_TOKEN"])

# 사용자 목록 가져오기
list_users_response = notion.users.list()
print(list_users_response)
```

### ✅ 장점
- 무료 플랜에서도 API 사용 가능
- Python 라이브러리가 잘 만들어져 있어 사용하기 쉬움
- 공식 문서가 잘 되어 있음
- AI 도구와 연결 가능

### ❌ 단점
- 마크다운을 노션 블록으로 변환하는 것이 복잡함 (노션은 자체 블록 구조 사용)
- API 속도 제한이 있음 (초당 3회)

---

## 2. 블로그/CMS 플랫폼 API

### 2.1 WordPress REST API

#### 📖 개요
워드프레스에 기본으로 포함된 API로, 프로그램으로 블로그 글을 자동으로 게시할 수 있습니다.

#### 🎯 주요 기능
- **자동 글 게시**: Python, JavaScript 등으로 글을 자동으로 올릴 수 있음
- **글 수정/삭제**: 이미 올린 글을 수정하거나 삭제할 수 있음
- **미디어 업로드**: 이미지나 파일도 자동으로 업로드 가능
- **SEO 플러그인 연동**: Yoast SEO 같은 플러그인과 함께 사용 가능

#### 💰 가격
- **무료**: WordPress 자체에 포함되어 있음 (호스팅 비용은 별도)
- WordPress.com 호스팅 사용 시: $4~$45/월

#### 🔑 인증 방법
- **Application Passwords** (앱 비밀번호): WordPress 5.6 이후 기본 포함
- 설정 → 사용자 → Application Passwords에서 토큰 생성

#### 📝 사용 예시 (Python)
```python
import requests

url = "https://yourwebsite.com/wp-json/wp/v2/posts"
headers = {
    "Authorization": "Basic YOUR_BASE64_TOKEN"
}
data = {
    "title": "API로 작성한 글",
    "content": "글 내용입니다.",
    "status": "publish"  # 바로 게시
}

response = requests.post(url, headers=headers, json=data)
```

#### ✅ 장점
- 무료로 사용 가능
- 매우 많은 사용자가 있어 자료가 풍부함
- SEO 최적화 도구가 많음
- 플러그인 생태계가 거대함

#### ❌ 단점
- 워드프레스 사이트를 먼저 만들어야 함
- 호스팅 비용이 별도로 필요

---

### 2.2 Ghost CMS API

#### 📖 개요
개발자 친화적인 블로그 플랫폼으로, 깔끔한 API를 제공합니다.

#### 🎯 주요 기능
- **여러 뉴스레터 발행**: 한 사이트에서 여러 뉴스레터를 만들 수 있음
- **회원 관리**: 유료 회원제 콘텐츠 운영 가능
- **소셜 웹 연동**: Mastodon, Bluesky, Threads 자동 공유 (2025년 추가)
- **Headless CMS**: API로만 콘텐츠를 관리하고 다른 프론트엔드 사용 가능
- **내장 분석 도구**: 방문자 통계 기본 제공

#### 💰 가격 (2026년 기준)
| 플랜 | 가격 (연간 결제) | 회원 수 | 플랫폼 수수료 |
|------|------------------|---------|---------------|
| **Starter** | $15/월 | 1,000명 | 0% |
| **Publisher** | $29/월 | 1,000명 | 0% |
| **Business** | $199/월 | 1,000명 | 0% |

> 💡 **무료 옵션**: 오픈소스라서 직접 서버에 설치하면 무료 (기술 지식 필요)
> 💳 **결제 수수료**: Stripe 수수료만 부담 (Ghost는 0% 수수료)

#### ✅ 장점
- 플랫폼 수수료 0% (Substack은 10% 가져감)
- API가 깔끔하고 사용하기 쉬움
- SEO 최적화 기본 탑재
- 현대적이고 빠른 디자인

#### ❌ 단점
- 호스팅 비용이 비싼 편 (직접 설치하면 저렴하지만 기술 필요)
- WordPress만큼 플러그인이 많지 않음

---

### 2.3 Medium API

#### 📖 개요
Medium 플랫폼에 자동으로 글을 게시할 수 있는 API입니다.

#### ⚠️ 중요 공지
**Medium API는 2023년 3월에 공식 지원이 중단되었습니다.**

#### 🎯 제한적인 기능
- 새 글 작성만 가능 (수정/삭제 불가)
- 내 글 목록 조회 불가
- 사용자 정보만 조회 가능

#### 💰 가격
- API 자체는 무료
- Medium 회원: $5/월 (읽기 위해 필요)

#### 🔑 토큰 발급
Medium 설정 → Integration tokens → Generate new token

#### ✅ 장점
- 무료로 사용 가능
- Medium 플랫폼의 큰 독자층 활용 가능

#### ❌ 단점
- **API 지원 중단됨** (공식 업데이트 없음)
- 기능이 매우 제한적 (글 수정도 안 됨)
- 자동화 도구들이 2017년쯤 대부분 작동 중단

> 💡 **추천**: Medium보다는 Ghost나 WordPress 사용을 권장합니다.

---

### 2.4 Hashnode API

#### 📖 개요
개발자를 위한 블로그 플랫폼으로, GraphQL API를 제공합니다.

#### 🎯 주요 기능
- **GraphQL API**: 현대적인 API 방식 사용
- **자동 게시**: 글을 바로 게시하거나 초안으로 저장 가능
- **개발자 친화적**: 기술 블로그에 최적화됨
- **무료 커스텀 도메인**: 자신의 도메인 사용 가능

#### 💰 가격
- **완전 무료**: 기본 기능 전부 무료
- API 속도 제한: 분당 20,000회 (매우 넉넉함!)

#### 🔑 인증 방법
Hashnode 설정 → Developer Settings → Generate new token

#### 📝 API 엔드포인트
```
https://gql.hashnode.com
```

#### 📝 사용 예시 (GraphQL)
```graphql
mutation PublishPost {
  publishPost(
    title: "내 블로그 글"
    contentMarkdown: "# 제목\n글 내용"
  ) {
    post {
      id
      slug
    }
  }
}
```

#### ✅ 장점
- 완전 무료
- API 속도 제한이 매우 넉넉함 (분당 20,000회)
- 개발자 커뮤니티가 활발함
- 마크다운 직접 지원

#### ❌ 단점
- 주로 개발자/기술 블로그 위주
- 일반 블로그로는 Ghost나 WordPress가 더 적합할 수 있음

---

## 3. 이미지 생성 API

### 3.1 OpenAI DALL-E / GPT Image API

#### 📖 개요
OpenAI에서 제공하는 AI 이미지 생성 API입니다.

#### 🎯 주요 모델 (2026년 기준)

| 모델 | 출시 시기 | 가격 (이미지당) | 특징 |
|------|-----------|-----------------|------|
| **GPT Image 1.5** | 2025년 후반 | $0.01 ~ $0.17 | 최신 플래그십 모델 |
| **GPT Image 1** | 이전 | $0.011 ~ $0.25 | 이전 플래그십 |
| **GPT Image 1 Mini** | - | $0.005 ~ $0.052 | 저렴한 옵션 (50-70% 절감) |
| **DALL-E 3** | 2023년 | $0.04 ~ $0.12 | 이전 세대 (여전히 사용 가능) |
| **DALL-E 2** | 2022년 | $0.016 ~ $0.02 | 레거시 모델 |

#### 💰 가격 예시
**GPT Image 1.5 (정사각형 이미지)**:
- Low 품질: $0.01
- Medium 품질: $0.04
- High 품질: $0.17

**GPT Image 1 Mini (저렴한 옵션)**:
- 플래그십 대비 50-70% 저렴

#### 📝 사용 방법
```python
import openai

response = openai.Image.create(
    model="gpt-image-1.5",
    prompt="노을이 지는 산의 풍경, 한국화 스타일",
    size="1024x1024",
    quality="high"
)

image_url = response['data'][0]['url']
```

#### ✅ 장점
- 품질이 매우 높음
- 다양한 가격대 선택 가능 (Mini ~ 1.5)
- OpenAI 계정만 있으면 바로 사용 가능
- 안정적인 API

#### ❌ 단점
- 무료 옵션 없음 (유료만 가능)
- 이미지당 비용이 누적됨

---

### 3.2 Midjourney API

#### 📖 개요
가장 유명한 AI 이미지 생성 도구 중 하나입니다.

#### ⚠️ 중요 공지
**Midjourney는 2026년 현재까지 공식 API를 제공하지 않습니다.**

#### 🔧 비공식 API 솔루션
공식 API가 없어서 여러 업체가 비공식 API를 제공하고 있습니다:

| 업체 | 가격 | 특징 |
|------|------|------|
| **ImagineAPI** | $39/월 | 900 이미지 크레딧 |
| **PiAPI** | $0.01/이미지 (종량제) | Midjourney 구독 별도 필요 |
| **Journey AI Art** | $6/월부터 | 무료: 4 크레딧/일 |
| **UserAPI** | $25/월 | 무료 플랜 50 크레딧 |

#### ⚠️ 위험 요소
- **Midjourney 이용 약관 위반**: 자동화는 약관 위반으로 계정 정지 위험
- 비공식 API는 언제든 작동 중단 가능

#### 💰 Midjourney 직접 사용 가격
- Basic: $10/월
- Standard: $30/월
- Pro: $60/월
- Mega: $120/월

> ⚠️ **추천하지 않음**: 공식 API가 없고 자동화 시 계정 정지 위험이 있어 프로덕션 환경에서는 사용하지 않는 것을 권장합니다.

---

### 3.3 Stable Diffusion API

#### 📖 개요
오픈소스 AI 이미지 생성 모델로, 다양한 방식으로 사용 가능합니다.

#### 💰 가격 옵션

**1. 완전 무료: 로컬 실행**
- Stable Diffusion을 자신의 컴퓨터에 설치해서 무료로 무제한 사용
- 필요한 것: 성능 좋은 GPU (예: NVIDIA RTX 3060 이상)

**2. 공식 Stable Diffusion API (Stability AI)**
| 플랜 | 가격 | 이미지 생성 | API 호출 |
|------|------|-------------|----------|
| **Basic** | $29/월 | 최대 13,000장 | 3,250회 |
| **Standard** | $49/월 | 최대 40,000장 | 10,000회 |
| **Premium** | $149/월 | 무제한 | 무제한 |

**3. 저렴한 대안 API**

| 서비스 | 가격 | 특징 |
|--------|------|------|
| **Runware** | - | 다른 업체 대비 90% 저렴, 40% 빠름 |
| **RunDiffusion** | $11~$100/월 | 다양한 플랜 |
| **WaveSpeedAI** | - | 600개 이상 모델 제공 |

#### ✅ 장점
- 오픈소스라 로컬에서 무료 사용 가능
- 다양한 API 제공 업체 선택 가능
- 커뮤니티가 크고 모델이 많음
- 커스터마이징 자유도가 높음

#### ❌ 단점
- 로컬 실행은 고성능 GPU 필요
- 초보자에게는 설정이 복잡할 수 있음
- DALL-E보다 품질이 약간 떨어질 수 있음

#### 💡 추천
- **무료 사용하고 싶다면**: 로컬 설치 (GPU 필요)
- **편하게 사용하고 싶다면**: RunDiffusion이나 Runware 같은 저렴한 API 서비스

---

### 3.4 Canva API

#### 📖 개요
유명한 디자인 도구 Canva의 API 기능입니다.

#### ⚠️ 중요 제약 사항
**Canva API는 Enterprise(대기업) 플랜에서만 사용 가능합니다.**

#### 💰 가격

**일반 사용자 (API 없음)**:
| 플랜 | 가격 | AI 이미지 생성 | API |
|------|------|----------------|-----|
| **Free** | 무료 | 제한적 | ❌ |
| **Pro** | $12.99/월 | 50~100장/월 | ❌ |
| **Enterprise** | 맞춤 가격 | 맞춤 설정 | ✅ |

#### 🎯 Canva Pro AI 기능
- 월 500 AI 크레딧 제공
- AI 이미지 생성: 5-10 크레딧/이미지
- 실제로 생성 가능한 이미지: 약 50-100장/월

#### 🔧 API 대안
Canva API가 너무 비싸서, 대신 사용할 수 있는 서비스들:
- **Templated.io**: 템플릿 기반 이미지 자동 생성
- **Contentdrips**: API 중심의 디자인 자동화

#### ✅ 장점
- 사용하기 매우 쉬운 UI
- 템플릿이 매우 많음
- 비디자이너도 쉽게 사용 가능

#### ❌ 단점
- **API는 Enterprise 플랜만 가능** (가격 비공개, 매우 비쌈)
- 자동화가 필요하면 다른 도구를 써야 함
- Pro 플랜은 API 없이 수동 작업만 가능

> 💡 **추천**: 자동화가 필요하다면 Stable Diffusion이나 DALL-E 사용. 수동으로 간단한 썸네일 만들기는 Canva Pro가 좋습니다.

---

### 📊 이미지 생성 API 종합 비교

| API | 무료 옵션 | 가격대 | 품질 | 자동화 | 추천 용도 |
|-----|----------|--------|------|--------|-----------|
| **DALL-E / GPT Image** | ❌ | $0.01~$0.17/장 | ⭐⭐⭐⭐⭐ | ✅ | 높은 품질 필요할 때 |
| **Midjourney** | ❌ | $10~$120/월 | ⭐⭐⭐⭐⭐ | ⚠️ (비공식) | 수동 사용만 |
| **Stable Diffusion** | ✅ (로컬) | $0~$149/월 | ⭐⭐⭐⭐ | ✅ | 예산 절약 |
| **Canva** | 제한적 | $0~$12.99/월 | ⭐⭐⭐ | ❌ (Enterprise만) | 간단한 디자인 |

---

## 4. 문서 변환 도구

### 4.1 Pandoc

#### 📖 개요
Pandoc은 거의 모든 문서 형식을 다른 형식으로 변환할 수 있는 강력한 오픈소스 도구입니다.

#### 🎯 변환 가능한 형식
- **입력**: Markdown, HTML, LaTeX, Word DOCX, ePub 등
- **출력**: PDF, DOCX, HTML, ePub, LaTeX 등

#### 💰 가격
- **완전 무료** (오픈소스)

#### 📦 설치 방법
```bash
# macOS
brew install pandoc

# Ubuntu/Debian
sudo apt install pandoc

# Windows
# https://pandoc.org/installing.html 에서 설치 파일 다운로드
```

#### 📝 사용 예시

**마크다운 → PDF**:
```bash
pandoc input.md -o output.pdf
```

**마크다운 → DOCX (워드 파일)**:
```bash
pandoc input.md -o output.docx
```

**여러 파일 합쳐서 PDF로**:
```bash
pandoc part01.md part02.md part03.md -o document.pdf
```

**PDF 생성 시 여백 설정**:
```bash
pandoc -s -V geometry:margin=1in -o documentation.pdf part01.md part02.md
```

#### ⚙️ PDF 생성 요구사항
PDF를 만들려면 LaTeX가 설치되어 있어야 합니다:
```bash
# macOS
brew install mactex-no-gui

# Ubuntu/Debian
sudo apt install texlive
```

#### ✅ 장점
- 완전 무료
- 거의 모든 문서 형식 지원
- 매우 강력한 커스터마이징 가능
- 명령줄에서 간단하게 사용

#### ❌ 단점
- 명령줄 사용이 처음에는 어려울 수 있음
- PDF 만들려면 LaTeX 설치 필요 (용량 큼)
- 디자인 커스터마이징은 복잡함

#### 💡 추천 사용 사례
- 마크다운 블로그 글 → PDF 백업
- 여러 마크다운 파일 → 하나의 문서 (PDF/DOCX)
- 기술 문서 자동 생성

---

### 4.2 WeasyPrint

#### 📖 개요
HTML/CSS를 PDF로 변환하는 Python 라이브러리입니다.

#### 🎯 주요 특징
- HTML + CSS를 PDF로 변환
- 웹 표준 지원 (CSS3 Flexbox, Grid 등)
- Python으로 사용하기 쉬움

#### 💰 가격
- **완전 무료** (오픈소스, BSD 라이선스)

#### 📦 설치 방법
```bash
pip install weasyprint
```

**시스템 요구사항**: Python 3.10 이상

#### 📝 사용 예시

**Python 코드**:
```python
from weasyprint import HTML

# HTML 파일을 PDF로 변환
HTML('document.html').write_pdf('output.pdf')

# URL을 PDF로 변환
HTML('https://example.com').write_pdf('page.pdf')

# HTML 문자열을 PDF로 변환
html_string = '<h1>제목</h1><p>내용입니다.</p>'
HTML(string=html_string).write_pdf('output.pdf')
```

#### 🎨 디자인 커스터마이징
CSS로 페이지 스타일을 완전히 제어할 수 있습니다:
```css
@page {
  size: A4;
  margin: 2cm;
}

h1 {
  color: #333;
  page-break-before: always;
}
```

#### ✅ 장점
- 완전 무료
- Python으로 사용하기 매우 쉬움
- CSS로 디자인 자유롭게 제어
- LaTeX 설치 불필요
- 웹 기술 (HTML/CSS) 그대로 사용

#### ❌ 단점
- Python 지식 필요
- Pandoc보다 기능이 적음 (HTML→PDF만 가능)

#### 💡 추천 사용 사례
- 블로그 글 (HTML) → PDF 변환
- 보고서 자동 생성 (Python 프로그램)
- 디자인이 복잡한 문서 (CSS 활용)

---

### 4.3 markdown-pdf (NPM 패키지)

#### 📖 개요
Node.js 환경에서 마크다운을 PDF로 변환하는 도구들입니다.

#### 🔧 주요 패키지

**1. md-to-pdf** (추천)
```bash
npm install -g md-to-pdf
```

**사용법**:
```bash
# CLI로 변환
md-to-pdf document.md

# JavaScript로 사용
const mdToPdf = require('md-to-pdf');
mdToPdf({ path: 'document.md' }).then(pdf => {
  console.log('PDF 생성 완료');
});
```

**2. mdpdf**
```bash
npm install -g @mdpdf/mdpdf
```

**사용법**:
```bash
mdpdf document.md output.pdf
```

#### 💰 가격
- **완전 무료** (오픈소스)

#### ✅ 장점
- Node.js 환경에서 사용하기 쉬움
- 코드 하이라이팅 지원
- 커스텀 CSS 적용 가능
- Headless Chrome 사용 (웹 브라우저처럼 렌더링)

#### ❌ 단점
- Node.js 설치 필요
- Pandoc보다 기능이 적음

#### 💡 추천 사용 사례
- Node.js 기반 프로젝트
- 마크다운 문서 자동 PDF 변환
- 간단한 블로그 글 PDF 저장

---

### 4.4 ePub (전자책) 생성

#### 📖 개요
ePub은 전자책 표준 형식으로, Kindle이나 전자책 리더에서 읽을 수 있습니다.

#### 🔧 도구 옵션

**1. Pandoc (추천)**
```bash
# 마크다운을 ePub으로 변환
pandoc book.md -o book.epub

# 여러 파일을 하나의 ePub으로
pandoc chapter1.md chapter2.md chapter3.md -o book.epub

# 메타데이터 추가
pandoc book.md -o book.epub --metadata title="책 제목" --metadata author="저자"
```

**2. Calibre**
- GUI 프로그램 (시각적으로 사용)
- 마크다운 → ePub, MOBI, AZW3 등 변환
- 전자책 라이브러리 관리 가능

**Calibre 명령줄 사용**:
```bash
ebook-convert input.md output.epub
```

**3. md2ebook (Python 도구)**
```bash
pip install md2ebook
md2ebook input.md -o output.epub
```

#### 💰 가격
- **모두 무료** (오픈소스)

#### 📖 Calibre 특징
- **무료 오픈소스**: 완전 무료
- **다양한 형식 지원**: ePub, MOBI, AZW3, PDF 등
- **라이브러리 관리**: 전자책 컬렉션 관리
- **메타데이터 편집**: 표지, 저자, 제목 등 편집
- **ePub 버전 선택**: ePub 2 (가장 호환성 높음) or ePub 3

#### ✅ 장점
- 무료로 전자책 만들기 가능
- Kindle 등 다양한 기기 지원
- Pandoc은 명령줄에서 간단하게 사용
- Calibre는 GUI로 쉽게 사용

#### ❌ 단점
- 전자책 형식 특성상 레이아웃 제어가 제한적
- 복잡한 디자인은 어려움

#### 💡 추천 사용 사례
- 블로그 글 모음집 → ePub 전자책
- 기술 문서 → Kindle용 MOBI 파일
- 시리즈 글 → 하나의 전자책으로 출판

---

### 📊 문서 변환 도구 종합 비교

| 도구 | 무료 | 입력 형식 | 출력 형식 | 사용 난이도 | 추천 용도 |
|------|------|-----------|-----------|-------------|-----------|
| **Pandoc** | ✅ | MD, HTML, DOCX 등 | PDF, DOCX, ePub 등 | ⭐⭐⭐ | 만능 변환기 |
| **WeasyPrint** | ✅ | HTML/CSS | PDF | ⭐⭐ | 디자인 자유도 높음 |
| **md-to-pdf** | ✅ | Markdown | PDF | ⭐⭐ | Node.js 프로젝트 |
| **Calibre** | ✅ | MD, ePub, MOBI 등 | ePub, MOBI, PDF | ⭐ (GUI) | 전자책 제작 |

---

## 5. 프로젝트 기록/변경 로그 자동화

### 5.1 git-cliff (추천 ⭐)

#### 📖 개요
Rust로 만든 매우 빠르고 강력한 Changelog(변경 기록) 자동 생성 도구입니다.

#### 🎯 주요 특징
- **Conventional Commits 지원**: 커밋 메시지 규칙에 따라 자동 분류
- **매우 빠름**: Rust로 작성되어 120ms 만에 생성 (다른 도구는 수 초 소요)
- **높은 커스터마이징**: 설정 파일로 원하는 형식 자유롭게 변경
- **여러 형식 출력**: Markdown, JSON 등

#### 💰 가격
- **완전 무료** (오픈소스)

#### 📦 설치 방법
```bash
# macOS
brew install git-cliff

# Linux
cargo install git-cliff

# npm으로도 설치 가능
npm install -g git-cliff
```

#### 📝 사용 예시

**기본 사용**:
```bash
# CHANGELOG.md 파일 생성
git cliff -o CHANGELOG.md

# 최근 3개 버전만
git cliff --latest

# 특정 버전 범위
git cliff v1.0.0..v2.0.0
```

#### ⚙️ 설정 파일 (cliff.toml)
```toml
[changelog]
header = """
# Changelog\n
모든 변경 사항은 이 파일에 기록됩니다.\n
"""

[git]
conventional_commits = true
filter_unconventional = true

[git.commit_parsers]
message = "^feat"
group = "✨ 새로운 기능"

message = "^fix"
group = "🐛 버그 수정"

message = "^docs"
group = "📝 문서"
```

#### 🎨 Conventional Commits 예시
```bash
# 새 기능
git commit -m "feat: 로그인 기능 추가"

# 버그 수정
git commit -m "fix: 비밀번호 유효성 검사 오류 수정"

# 문서 변경
git commit -m "docs: README 업데이트"

# 리팩토링
git commit -m "refactor: 사용자 인증 코드 개선"
```

#### ✅ 장점
- **매우 빠름** (다른 도구 대비 10배 이상 빠름)
- 커스터마이징이 자유로움
- 현대적이고 활발하게 유지보수됨
- 설정이 직관적

#### ❌ 단점
- Rust 설치가 필요할 수 있음 (npm 버전도 있음)
- 커밋 메시지 규칙을 따라야 효과적 (Conventional Commits)

---

### 5.2 conventional-changelog

#### 📖 개요
Node.js 기반의 전통적인 changelog 생성 도구입니다.

#### 📦 설치 방법
```bash
npm install -g conventional-changelog-cli
```

#### 📝 사용 예시
```bash
# CHANGELOG.md 생성/업데이트
conventional-changelog -p angular -i CHANGELOG.md -s

# 첫 번째 릴리스
conventional-changelog -p angular -i CHANGELOG.md -s -r 0
```

#### ✅ 장점
- 오래되고 안정적
- Angular, React 등 큰 프로젝트에서 사용
- npm 생태계와 잘 통합됨

#### ❌ 단점
- git-cliff보다 느림
- 설정이 복잡함
- 최근 업데이트가 적음

---

### 5.3 auto-changelog

#### 📖 개요
간단한 명령어로 changelog를 자동 생성하는 도구입니다.

#### 📦 설치 방법
```bash
npm install -g auto-changelog
```

#### 📝 사용 예시
```bash
# CHANGELOG.md 생성
auto-changelog

# 특정 버전부터
auto-changelog --starting-version 1.0.0
```

#### ✅ 장점
- 설정 없이 바로 사용 가능
- 간단한 사용법

#### ❌ 단점
- 커스터마이징 제한적
- git-cliff보다 기능이 적음

---

### 📊 Changelog 도구 종합 비교

| 도구 | 무료 | 속도 | 커스터마이징 | 추천도 | 특징 |
|------|------|------|--------------|--------|------|
| **git-cliff** | ✅ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Rust, 매우 빠름, 현대적 |
| **conventional-changelog** | ✅ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | Node.js, 전통적, 안정적 |
| **auto-changelog** | ✅ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ | 간단함, 설정 불필요 |

> 💡 **추천**: 새 프로젝트라면 **git-cliff**를 사용하세요. 속도가 빠르고 기능이 강력합니다.

---

## 6. 종합 요약 및 추천

### 📌 CPO 부서를 위한 도구 조합 추천

#### 🥇 최우선 추천 조합 (무료 중심)

```
1️⃣ 콘텐츠 관리: Notion API (무료)
2️⃣ 블로그 게시: Hashnode API (무료) or WordPress API (호스팅 비용만)
3️⃣ 이미지 생성: Stable Diffusion 로컬 설치 (무료, GPU 필요)
4️⃣ 문서 변환: Pandoc (무료)
5️⃣ Changelog 생성: git-cliff (무료)
```

#### 💰 예산이 있을 경우 (품질 우선)

```
1️⃣ 콘텐츠 관리: Notion API Pro ($10/월)
2️⃣ 블로그 게시: Ghost CMS ($15/월) or WordPress Premium
3️⃣ 이미지 생성: OpenAI GPT Image 1.5 (종량제 $0.01~0.17/장)
4️⃣ 문서 변환: Pandoc + WeasyPrint (무료)
5️⃣ Changelog 생성: git-cliff (무료)
```

---

### 📊 상황별 추천

#### 상황 1: 블로그 자동 게시 시스템 만들기
```
✅ 추천: Hashnode API (무료, GraphQL, 개발자 친화적)
✅ 대안: WordPress API (플러그인 많음, SEO 좋음)
❌ 비추천: Medium API (지원 중단됨)
```

#### 상황 2: 블로그 썸네일 자동 생성
```
✅ 추천 (무료): Stable Diffusion 로컬 설치
✅ 추천 (유료): OpenAI GPT Image 1.5 or Mini
❌ 비추천: Midjourney (공식 API 없음, 계정 정지 위험)
❌ 비추천: Canva API (Enterprise만 가능, 매우 비쌈)
```

#### 상황 3: 마크다운 글을 PDF/ePub으로 변환
```
✅ 추천: Pandoc (무료, 만능, 강력함)
✅ 보조: Calibre (ePub 전자책 제작)
✅ Python 프로젝트: WeasyPrint (HTML→PDF)
```

#### 상황 4: Git 커밋 기록을 자동으로 Changelog 생성
```
✅ 추천: git-cliff (무료, 빠름, 현대적)
✅ 대안: conventional-changelog (안정적, Node.js)
```

---

### 💡 실전 워크플로우 예시

#### 워크플로우 1: 블로그 포스팅 자동화
```
1. 마크다운으로 글 작성
2. git-cliff로 변경 사항 Changelog 자동 생성
3. OpenAI API로 썸네일 이미지 자동 생성
4. Hashnode API로 블로그에 자동 게시
5. Notion API로 발행 기록 자동 저장
```

#### 워크플로우 2: 전자책 제작
```
1. 여러 마크다운 파일로 챕터 작성
2. Pandoc으로 하나의 ePub 파일로 병합
3. Calibre로 메타데이터 추가 및 표지 설정
4. MOBI 변환하여 Kindle 업로드
```

#### 워크플로우 3: 프로젝트 문서 자동 생성
```
1. 코드 변경 사항 커밋 (Conventional Commits)
2. git-cliff로 CHANGELOG.md 자동 업데이트
3. Pandoc으로 마크다운 문서들을 PDF로 변환
4. Notion API로 릴리스 노트 자동 기록
```

---

### ⚠️ 주의사항

#### 1. API 사용 시 반드시 확인할 것
- **속도 제한 (Rate Limit)**: API 호출 횟수 제한 확인
- **비용**: 종량제는 예상치 못한 비용 발생 가능
- **인증 토큰 보안**: 토큰이 유출되면 타인이 사용 가능

#### 2. 무료 vs 유료 선택 기준
- **무료가 적합한 경우**: 테스트, 소규모 프로젝트, 학습 목적
- **유료가 필요한 경우**: 프로덕션 환경, 대량 처리, 기술 지원 필요

#### 3. 오픈소스 도구 사용 시
- 커뮤니티 활발한지 확인 (최근 업데이트 날짜 확인)
- 문서가 잘 되어 있는지 확인
- 라이선스 확인 (상업적 사용 가능한지)

---

### 📚 참고 자료 (Sources)

#### Notion API
- [Notion Pricing](https://www.notion.com/pricing)
- [Notion API Documentation](https://developers.notion.com)
- [notion-client Python library](https://pypi.org/project/notion-client/)
- [Notion SDK Python](https://github.com/ramnes/notion-sdk-py)

#### 블로그/CMS API
- [WordPress REST API Documentation](https://developer.wordpress.org/rest-api/)
- [Ghost Pricing](https://ghost.org/pricing)
- [Hashnode API Documentation](https://docs.hashnode.com/quickstart/introduction)
- [Medium API GitHub](https://github.com/Medium/medium-api-docs)

#### 이미지 생성 API
- [OpenAI Pricing](https://openai.com/api/pricing/)
- [OpenAI Image Pricing Calculator](https://costgoat.com/pricing/openai-images)
- [Best Midjourney APIs 2026](https://www.myarchitectai.com/blog/midjourney-apis)
- [Stable Diffusion API Pricing](https://platform.stability.ai/pricing)
- [Runware AI](https://runware.ai/)
- [Canva Pricing](https://www.withorb.com/blog/canva-pricing)

#### 문서 변환 도구
- [Pandoc Documentation](https://pandoc.org/MANUAL.html)
- [WeasyPrint](https://weasyprint.org/)
- [md-to-pdf npm](https://www.npmjs.com/package/md-to-pdf)
- [Calibre ebook-convert](https://manual.calibre-ebook.com/generated/en/ebook-convert.html)

#### Changelog 도구
- [git-cliff](https://git-cliff.org/)
- [git-cliff GitHub](https://github.com/orhun/git-cliff)
- [Conventional Commits](https://www.conventionalcommits.org/en/about/)

---

## ✅ 결론

CPO(출판/콘텐츠/기록 관리) 부서를 위한 2026년 최신 API와 도구들을 모두 조사했습니다.

### 핵심 요약:
1. **무료로 시작 가능**: Notion API, Hashnode, Pandoc, git-cliff 모두 무료
2. **자동화 가능**: Python/Node.js로 전체 워크플로우 자동화 가능
3. **확장 가능**: 무료로 시작해서 필요 시 유료 플랜으로 업그레이드

### 다음 단계:
1. Notion API 토큰 발급 및 테스트
2. Hashnode 계정 생성 및 API 토큰 발급
3. Pandoc 설치 및 마크다운→PDF 변환 테스트
4. git-cliff 설치 및 Changelog 자동 생성 테스트

궁금한 점이나 구체적인 구현 방법이 필요하시면 언제든 말씀해주세요!