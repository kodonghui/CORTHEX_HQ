# README.md

내용을 입력하세요.
# LEET MASTER - 추리논증 학습 플랫폼

법학적성시험(LEET) 추리논증 문제를 풀고, AI 해설과 개인 피드백을 받는 학습 플랫폼입니다.

## 🌐 접속 URL

- **Production**: https://leet-master.pages.dev
- **GitHub**: https://github.com/kodonghui/leet-master

## 📋 프로젝트 개요

| 항목 | 내용 |
|------|------|
| **목표** | LEET 추리논증 학습 효율 극대화 |
| **대상** | 법학전문대학원 입학 준비 수험생 |
| **특징** | AI 기반 개인화 피드백 + 크레딧 기반 과금 |
| **문제 수** | 715문제 (2009년 예비~2026년) |

## ✅ 구현된 기능

### 핵심 기능
- [x] 문제 풀이 시스템 (715문제, 연도별 필터링)
- [x] AI 통합 해설 (Claude + GPT + Gemini 기반)
- [x] AI 개인 피드백 (수준별: 간단/상세/심층)
- [x] 사용자 인증 (회원가입, 로그인, JWT)
- [x] 학습 통계 및 풀이 기록
- [x] 학습 달력 (일별 학습량 시각화)

### 관리자 기능
- [x] 크레딧 관리 대시보드
- [x] 사용자별 크레딧 지급/차감
- [x] 피드백 로그 조회 및 삭제
- [x] 공지사항 관리
- [x] 문제 업로드 (TSV/CSV)
- [x] 결제 관리 (수동 확인)

### 크레딧 시스템
- [x] 비용 기반 크레딧 차감 (토큰 ÷10 × 2배 마진)
- [x] 크레딧 충전 (계좌이체 → 관리자 확인 → 지급)
- [x] 충전 확인 모달
- [x] 크레딧 상품 관리

### UI/UX
- [x] 다크 모드 기본
- [x] 모바일 반응형 디자인
- [x] 모바일 문제 선택 (플로팅 버튼 + 바텀시트)
- [x] 햄버거 메뉴 (오버레이 + 스크롤 방지)
- [x] 정답/오답/미풀이 색상 구분
- [x] 공지사항 알림 배지

## 🛠 기술 스택

| 영역 | 기술 |
|------|------|
| Frontend | HTML + Tailwind CSS (CDN) + Vanilla JS |
| Backend | Hono (TypeScript) |
| Database | Cloudflare D1 (SQLite) |
| AI | OpenAI GPT API |
| Hosting | Cloudflare Pages |
| Version Control | GitHub |

## 📁 프로젝트 구조

```
webapp/
├── src/
│   ├── index.tsx              # 메인 앱 & HTML 템플릿
│   └── routes/
│       ├── problems.ts        # 문제 조회 API
│       ├── answers.ts         # 답안 제출 API
│       ├── auth.ts            # 인증 API
│       ├── feedback.ts        # AI 피드백 API
│       ├── admin.ts           # 관리자 API
│       ├── announcements.ts   # 공지사항 API
│       ├── payments.ts        # 결제 API
│       └── stats.ts           # 통계 API
├── public/static/
│   ├── app.js                 # 프론트엔드 JS
│   └── style.css              # 커스텀 스타일
├── migrations/                # D1 마이그레이션
├── AI_PLAYBOOK.md             # AI 개발자 작업 규칙
├── STATUS.md                  # 현재 상태 및 TODO
├── wrangler.jsonc             # Cloudflare 설정
└── package.json
```

## 💳 크레딧 상품

| 상품 | 크레딧 | 가격 | 보너스 |
|------|--------|------|--------|
| 스타터 | 1,000 | 1,000원 | - |
| 베이직 | 5,000 | 4,500원 | +500 |
| 스탠다드 | 10,000 | 8,000원 | +2,000 |
| 프리미엄 | 30,000 | 20,000원 | +10,000 |

## 💰 입금 계좌

**기업은행 59603070001013 고동희**

## 🚀 로컬 개발

```bash
# 의존성 설치
npm install

# D1 마이그레이션 (로컬)
npm run db:migrate:local

# 빌드
npm run build

# 개발 서버 (PM2)
pm2 start ecosystem.config.cjs

# 테스트
curl http://localhost:3000/api/health
```

## 📝 환경 변수

### 로컬 (.dev.vars)
```
JWT_SECRET=your-jwt-secret
OPENAI_API_KEY=your-openai-api-key
```

### 프로덕션 (Cloudflare Secrets)
```bash
npx wrangler pages secret put JWT_SECRET --project-name leet-master
npx wrangler pages secret put OPENAI_API_KEY --project-name leet-master
```

## 📊 API 엔드포인트

### 공개 API
| Method | Path | 설명 |
|--------|------|------|
| GET | /api/health | 헬스체크 |
| GET | /api/problems | 문제 목록 |
| POST | /api/auth/register | 회원가입 |
| POST | /api/auth/login | 로그인 |

### 인증 필요 API
| Method | Path | 설명 |
|--------|------|------|
| GET | /api/auth/me | 내 정보 |
| POST | /api/answers/submit | 답안 제출 |
| POST | /api/feedback | AI 피드백 요청 |
| GET | /api/stats | 학습 통계 |
| POST | /api/payments/request | 결제 요청 |

### 관리자 API
| Method | Path | 설명 |
|--------|------|------|
| POST | /api/admin/credits/grant | 크레딧 지급 |
| DELETE | /api/feedback/logs | 피드백 로그 삭제 |
| POST | /api/payments/:id/confirm | 결제 확인 |

## 🔜 다음 단계 (P1)

- [ ] 로고 개선 (다이아몬드 L, 네온 파랑→보라)
- [ ] 풀이기록 UI 개선
- [ ] 수익분석 메뉴 정리

---

**Last Updated**: 2026-02-06
`