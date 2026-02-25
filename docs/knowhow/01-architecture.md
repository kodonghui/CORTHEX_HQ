# 01. 대규모 아키텍처 리빌딩 패턴

> 비유: 아파트 리모델링 — 사람 살면서 한 방씩 공사하는 것

---

## 언제 필요한가?

- 코드가 3,000줄 넘어갈 때
- "이거 어디 있더라?" 하는 순간이 잦을 때
- 새 기능 추가할 때마다 다른 곳이 깨질 때
- 파일 1개에 모든 기능이 몰려있을 때

## 핵심 원칙 5가지

### 1. 점진적 분리 (Big Bang 금지)
```
❌ "전체를 다시 짜자" → 6개월 걸리고 결국 포기
✅ "이번 주는 인증만 분리하자" → 1주일에 1모듈씩
```

### 2. 상태 중앙 집중 → 분산
```
Before: app.state = { user, settings, trading, chat, ... } (한 덩어리)
After:  각 모듈이 자기 상태만 관리 + 이벤트로 통신
```

### 3. Lazy Loading (필요할 때만 로드)
```javascript
// ❌ 앱 시작 시 모든 기능 로드
import TradingModule from './trading';
import AnalyticsModule from './analytics';

// ✅ 해당 탭 진입 시에만 로드
async switchTab(tab) {
  if (tab === 'trading') await import('./trading');
}
```

### 4. API → Handler → 모듈 3계층
```
사용자 요청 → API 라우터 → Handler (비즈니스 로직) → DB/외부서비스
                              ↑ 여기만 테스트하면 됨
```

### 5. 설정 외부화
```yaml
# ❌ 코드에 하드코딩
model = "claude-sonnet-4-20250514"

# ✅ 설정 파일에서 읽기
model = config.models['default']
```

## CORTHEX 실전 사례

| 단계 | 분리 대상 | 효과 |
|------|-----------|------|
| 1 | `mini_server.py` → handler 8개 분리 | 8,500줄 → 평균 500줄/파일 |
| 2 | `config/agents.yaml` + `models.yaml` | 모델 변경 시 코드 수정 0건 |
| 3 | `_loadScript()` 동적 CDN 로드 | 초기 로딩 2.8초 → 1.2초 |
| 4 | `template x-if` lazy 렌더링 | DOM 노드 8,000 → 3,000 |

## 체크리스트

- [ ] 단일 파일 3,000줄 이상 → 모듈 분리 계획
- [ ] 전역 상태 20개 이상 → 도메인별 분산
- [ ] 외부 의존성 → 설정 파일로 외부화
- [ ] 초기 로딩 → lazy load 패턴 적용
- [ ] 테스트 가능한 handler 계층 분리
