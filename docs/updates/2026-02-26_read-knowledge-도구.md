# read_knowledge 도구 + 리트마스터 지식 주입

> 2026-02-26 | 브랜치: claude/notion-cleanup

---

## 배경

- `knowledge/leet_master/product_info.md` 가 빈 템플릿 상태 → 팀장들이 리트마스터를 전혀 참고 못함
- `knowledge/` 폴더를 매 요청마다 시스템 프롬프트에 주입하면 ~2,000~3,000 토큰 낭비 (21일 논의)
- **해결**: on-demand 도구로 필요할 때만 호출 → 평소 토큰 0, 호출 시 ~1,500 토큰

---

## 변경 사항

### 1. product_info.md 채우기
- `knowledge/leet_master/product_info.md`: GitHub 저장소(https://github.com/kodonghui/leet-master) 완전 분석 후 작성
  - 서비스 정의, 타겟(법전원 수험생 ~12,000명/년), 기능 현황(✅/⬜), 크레딧 구조
  - 경쟁사 분석(메가로스쿨/이그잼/프라임/큐나이), 핵심 가설, 팀장별 관여 범위

### 2. read_knowledge 도구 신규 구현
- `src/tools/read_knowledge.py` 생성
  - `division` 파라미터: leet_master / finance / publishing / shared / flowcharts
  - `file` 파라미터: 특정 파일명 (없으면 목록 반환, 둘 다 없으면 전체 목록)
  - LLM 호출 없음 — 순수 파일 읽기 → 토큰 최소화

### 3. 도구 등록
- `src/tools/pool.py`: `_imports` 딕셔너리에 `read_knowledge` 추가
- `config/tools.yaml`: 스키마 + 파라미터 등록
- `config/agents.yaml`: 5개 팀장 allowed_tools에 추가
  - 전략팀장(cso_manager), 법무팀장(clo_manager), 마케팅팀장(cmo_manager)
  - 금융분석팀장(cio_manager), 콘텐츠팀장(cpo_manager)
- `config/tools.json` + `config/agents.json` 삭제 (서버 재시작 시 YAML에서 재생성)

---

## 사용 예시 (에이전트 기준)

```
read_knowledge(division="leet_master")                  # 파일 목록 조회
read_knowledge(division="leet_master", file="product_info")  # 제품 정보 전체 조회
read_knowledge()                                        # 전체 knowledge 목록
```

---

## 확인 방법

1. 전략팀장에게 "리트마스터 예창패 사업계획서 전략 분석해줘" 요청
2. 팀장이 `read_knowledge(division="leet_master", file="product_info")` 호출 → 제품 정보 참고 후 분석
