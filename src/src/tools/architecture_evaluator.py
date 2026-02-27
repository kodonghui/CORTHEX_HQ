"""
소프트웨어 아키텍처 평가 도구 (Architecture Evaluator)

ISO/IEC 25010:2023 품질모델 기반으로 소프트웨어 아키텍처를 교수급 수준에서
정밀 진단합니다. SOLID 원칙 준수도, 디자인 패턴 적합성, 안티패턴 탐지,
결합도/응집도 분석, 마이그레이션 전략, DDD 도메인 주도 설계까지 8가지 관점의
종합 아키텍처 리포트를 제공합니다.

학술 근거:
  - ISO/IEC 25010:2023 — Systems and Software Quality Requirements and Evaluation (SQuaRE)
  - Robert C. Martin, "Clean Architecture" (2017) — SOLID 원칙 + 의존성 역전
  - Eric Evans, "Domain-Driven Design: Tackling Complexity in the Heart of Software" (2003)
  - Martin Fowler, "Patterns of Enterprise Application Architecture" (2002)
  - Erich Gamma et al., "Design Patterns: Elements of Reusable Object-Oriented Software" (GoF, 1994)
  - Len Bass, Paul Clements, Rick Kazman, "Software Architecture in Practice" (4th ed., 2021)
  - Mark Richards & Neal Ford, "Fundamentals of Software Architecture" (2020)

사용 방법:
  - action="evaluate"    : 아키텍처 종합 평가 (ISO/IEC 25010 품질모델 기반)
  - action="solid"       : SOLID 원칙 준수도 분석
  - action="patterns"    : 디자인 패턴 적합성 분석 (GoF 23 패턴)
  - action="antipatterns" : 안티패턴 탐지 (Big Ball of Mud, God Object 등)
  - action="coupling"    : 결합도/응집도 분석 (Afferent/Efferent Coupling)
  - action="migration"   : 아키텍처 마이그레이션 전략 (Strangler Fig, CQRS 등)
  - action="ddd"         : DDD 도메인 주도 설계 분석
  - action="full"        : 전체 종합 리포트 (asyncio.gather 병렬 실행)

필요 환경변수: 없음 (순수 LLM 분석)
필요 라이브러리: 없음 (표준 라이브러리만 사용)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.architecture_evaluator")

# ══════════════════════════════════════════════════════════════════════
#  ISO/IEC 25010:2023 — 8대 소프트웨어 품질 특성
# ══════════════════════════════════════════════════════════════════════

_ISO25010_QUALITIES: dict[str, dict[str, Any]] = {
    "functional_suitability": {
        "name_ko": "기능 적합성",
        "name_en": "Functional Suitability",
        "sub_chars": ["기능 완전성", "기능 정확성", "기능 적절성"],
        "description": "소프트웨어가 명시적·암묵적 요구사항을 충족하는 정도",
        "weight": 1.2,
        "evaluation_criteria": [
            "요구사항 대비 구현 범위 (Coverage)",
            "비즈니스 규칙 정확성 (Correctness)",
            "기능 목적 적절성 (Appropriateness)",
        ],
    },
    "performance_efficiency": {
        "name_ko": "성능 효율성",
        "name_en": "Performance Efficiency",
        "sub_chars": ["시간 반응성", "자원 활용률", "용량"],
        "description": "주어진 조건에서 사용하는 자원 양 대비 성능 수준",
        "weight": 1.1,
        "evaluation_criteria": [
            "응답 시간 (P50/P95/P99)",
            "CPU/메모리 사용률",
            "동시 처리 용량 (Throughput)",
        ],
    },
    "compatibility": {
        "name_ko": "호환성",
        "name_en": "Compatibility",
        "sub_chars": ["공존성", "상호운용성"],
        "description": "다른 시스템과 정보를 공유하며 공존할 수 있는 정도",
        "weight": 0.9,
        "evaluation_criteria": [
            "API 호환성 (하위/상위)",
            "데이터 포맷 표준 준수",
            "서드파티 통합 용이성",
        ],
    },
    "usability": {
        "name_ko": "사용성",
        "name_en": "Usability",
        "sub_chars": ["인지 용이성", "학습 용이성", "운용 용이성", "오류 방지", "접근성"],
        "description": "사용자가 효과적·효율적으로 사용할 수 있는 정도",
        "weight": 0.8,
        "evaluation_criteria": [
            "API/인터페이스 직관성",
            "개발자 온보딩 시간",
            "에러 메시지 명확성",
        ],
    },
    "reliability": {
        "name_ko": "신뢰성",
        "name_en": "Reliability",
        "sub_chars": ["성숙성", "가용성", "장애 허용성", "복구 가능성"],
        "description": "지정된 조건에서 시스템이 기능을 수행하는 정도",
        "weight": 1.2,
        "evaluation_criteria": [
            "MTBF (Mean Time Between Failures)",
            "가용률 (99.9% / 99.99%)",
            "장애 복구 시간 (MTTR)",
            "Graceful Degradation 지원 여부",
        ],
    },
    "security": {
        "name_ko": "보안",
        "name_en": "Security",
        "sub_chars": ["기밀성", "무결성", "부인방지", "책임추적성", "인증"],
        "description": "정보와 데이터를 보호하는 정도",
        "weight": 1.3,
        "evaluation_criteria": [
            "인증/인가 메커니즘",
            "데이터 암호화 (전송/저장)",
            "입력 검증 및 SQL Injection 방지",
            "감사 로그 (Audit Trail)",
        ],
    },
    "maintainability": {
        "name_ko": "유지보수성",
        "name_en": "Maintainability",
        "sub_chars": ["모듈성", "재사용성", "분석 가능성", "수정 가능성", "테스트 용이성"],
        "description": "수정·개선의 효과성과 효율성",
        "weight": 1.3,
        "evaluation_criteria": [
            "모듈 간 결합도 (Coupling)",
            "모듈 내 응집도 (Cohesion)",
            "코드 중복률 (DRY 원칙)",
            "테스트 커버리지",
            "변경 영향 범위 (Blast Radius)",
        ],
    },
    "portability": {
        "name_ko": "이식성",
        "name_en": "Portability",
        "sub_chars": ["적응성", "설치 용이성", "대체 용이성"],
        "description": "다른 환경으로 이전할 수 있는 정도",
        "weight": 0.8,
        "evaluation_criteria": [
            "환경 의존성 추상화 수준",
            "컨테이너화 가능성",
            "클라우드 벤더 종속성 (Lock-in)",
        ],
    },
}

# ══════════════════════════════════════════════════════════════════════
#  아키텍처 패턴 (Richards & Ford, 2020)
# ══════════════════════════════════════════════════════════════════════

_ARCHITECTURE_PATTERNS: dict[str, dict[str, Any]] = {
    "layered": {
        "name_ko": "계층형 아키텍처",
        "name_en": "Layered Architecture",
        "description": "Presentation → Business → Persistence → Database 계층 분리",
        "pros": ["단순 명확", "관심사 분리", "테스트 용이"],
        "cons": ["성능 오버헤드 (레이어 통과)", "확장 어려움", "모놀리식 경향"],
        "best_for": "소규모 비즈니스 앱, 초기 MVP, 교육/학습 프로젝트",
        "star_rating": 3,
        "reference": "Richards & Ford (2020), Ch.10",
    },
    "microservices": {
        "name_ko": "마이크로서비스 아키텍처",
        "name_en": "Microservices Architecture",
        "description": "독립 배포 가능한 소규모 서비스들의 조합",
        "pros": ["독립 배포", "기술 스택 자유도", "팀 자율성", "확장 용이"],
        "cons": ["운영 복잡성", "분산 트랜잭션", "네트워크 레이턴시", "디버깅 난이도"],
        "best_for": "대규모 팀, 트래픽 변동 큰 서비스, 다양한 기술 스택 필요 시",
        "star_rating": 4,
        "reference": "Sam Newman, 'Building Microservices' (2021)",
    },
    "event_driven": {
        "name_ko": "이벤트 주도 아키텍처",
        "name_en": "Event-Driven Architecture",
        "description": "이벤트 발행/구독으로 서비스 간 비동기 통신",
        "pros": ["느슨한 결합", "높은 확장성", "실시간 처리", "이벤트 소싱 가능"],
        "cons": ["이벤트 순서 보장 어려움", "디버깅 복잡", "최종 일관성(Eventual Consistency)"],
        "best_for": "실시간 데이터 처리, IoT, 금융 거래, 알림 시스템",
        "star_rating": 4,
        "reference": "Fowler, 'Event Sourcing' (2005); Hohpe & Woolf, 'Enterprise Integration Patterns' (2003)",
    },
    "hexagonal": {
        "name_ko": "헥사고날(포트-어댑터) 아키텍처",
        "name_en": "Hexagonal Architecture (Ports & Adapters)",
        "description": "도메인 로직을 중심에 두고 외부 의존성을 포트/어댑터로 격리",
        "pros": ["도메인 중심", "테스트 용이 (Mock 교체)", "외부 의존성 격리"],
        "cons": ["과도한 추상화 위험", "초기 설계 비용", "소규모 프로젝트에는 과잉"],
        "best_for": "복잡한 도메인 로직, DDD 적용 프로젝트, 장기 유지보수 필요 시",
        "star_rating": 5,
        "reference": "Alistair Cockburn (2005); Robert C. Martin, 'Clean Architecture' (2017)",
    },
    "cqrs": {
        "name_ko": "CQRS 아키텍처",
        "name_en": "Command Query Responsibility Segregation",
        "description": "명령(쓰기)과 조회(읽기) 모델을 분리하여 각각 최적화",
        "pros": ["읽기/쓰기 독립 확장", "복잡한 도메인 모델링", "이벤트 소싱 결합 가능"],
        "cons": ["복잡성 증가", "최종 일관성 관리", "동기화 로직 필요"],
        "best_for": "읽기/쓰기 비율 비대칭 서비스, 복잡한 비즈니스 규칙",
        "star_rating": 4,
        "reference": "Greg Young (2010); Fowler, 'CQRS' (2011)",
    },
    "serverless": {
        "name_ko": "서버리스 아키텍처",
        "name_en": "Serverless Architecture",
        "description": "FaaS(Function as a Service) 기반 이벤트 트리거 실행",
        "pros": ["운영 부담 최소", "자동 확장", "사용량 과금", "빠른 프로토타이핑"],
        "cons": ["콜드 스타트", "벤더 종속", "실행 시간 제한", "로컬 디버깅 어려움"],
        "best_for": "이벤트 기반 작업, API 게이트웨이, 주기적 배치, 초기 스타트업",
        "star_rating": 3,
        "reference": "Mike Roberts, 'Serverless Architectures' (2018)",
    },
}

# ══════════════════════════════════════════════════════════════════════
#  안티패턴 목록 (Brown et al., "AntiPatterns" 1998; Fowler 2002)
# ══════════════════════════════════════════════════════════════════════

_ANTIPATTERNS: dict[str, dict[str, Any]] = {
    "big_ball_of_mud": {
        "name_ko": "거대한 진흙 공 (Big Ball of Mud)",
        "severity": "치명적",
        "description": "구조 없이 무질서하게 성장한 시스템. 모듈 경계 없음",
        "symptoms": ["모든 모듈이 모든 모듈에 의존", "변경 시 예상치 못한 곳에서 버그", "새 개발자 온보딩 수주일 소요"],
        "remedy": "모듈 경계 재설정 + Strangler Fig 점진적 리팩토링",
        "reference": "Foote & Yoder (1999)",
    },
    "god_object": {
        "name_ko": "신 객체 (God Object)",
        "severity": "심각",
        "description": "하나의 클래스/모듈이 너무 많은 책임을 가짐 (SRP 위반)",
        "symptoms": ["하나의 파일이 1000줄 이상", "거의 모든 변경이 이 파일을 수정", "테스트 작성 불가능"],
        "remedy": "단일 책임 원칙(SRP) 적용하여 클래스 분할",
        "reference": "Riel, 'Object-Oriented Design Heuristics' (1996)",
    },
    "spaghetti_code": {
        "name_ko": "스파게티 코드",
        "severity": "심각",
        "description": "제어 흐름이 복잡하게 얽혀 추적 불가능한 코드",
        "symptoms": ["깊은 중첩 (3단계 이상 if/for)", "goto 또는 예외 기반 흐름 제어", "순환 복잡도(Cyclomatic) 20 이상"],
        "remedy": "메서드 추출 + 전략 패턴/상태 패턴 적용",
        "reference": "Martin, 'Clean Code' (2008)",
    },
    "golden_hammer": {
        "name_ko": "황금 망치 (Golden Hammer)",
        "severity": "보통",
        "description": "하나의 기술/패턴을 모든 문제에 적용하려는 경향",
        "symptoms": ["모든 데이터를 RDB에 저장 (캐시/검색 포함)", "모든 통신을 REST로만 처리", "모든 로직을 하나의 언어로만 구현"],
        "remedy": "문제에 맞는 기술 선택 (Polyglot Persistence, 적절한 통신 프로토콜)",
        "reference": "Brown et al., 'AntiPatterns' (1998)",
    },
    "lava_flow": {
        "name_ko": "용암 흐름 (Lava Flow)",
        "severity": "보통",
        "description": "죽은 코드/레거시가 굳어져 제거할 수 없는 상태",
        "symptoms": ["아무도 이해 못하는 코드가 프로덕션에 존재", "삭제하면 뭔가 깨질까봐 방치", "주석 처리된 코드 블록 다수"],
        "remedy": "테스트 커버리지 확보 후 점진적 제거 + Git 히스토리 활용",
        "reference": "Brown et al., 'AntiPatterns' (1998)",
    },
    "distributed_monolith": {
        "name_ko": "분산 모놀리스",
        "severity": "심각",
        "description": "마이크로서비스 형태이지만 실제로는 강하게 결합된 모놀리스",
        "symptoms": ["서비스 A 배포 시 B, C도 함께 배포 필요", "공유 DB 직접 접근", "동기 호출 체인이 5단계 이상"],
        "remedy": "서비스 경계 재정의 + 비동기 통신 도입 + 공유 DB 분리",
        "reference": "Sam Newman, 'Building Microservices' (2021)",
    },
    "premature_optimization": {
        "name_ko": "성급한 최적화",
        "severity": "보통",
        "description": "프로파일링 없이 추측으로 최적화. 가독성·유지보수성 저하",
        "symptoms": ["읽기 어려운 비트 연산/인라인 코드", "캐시가 오히려 버그 유발", "측정 없이 '느릴 것 같아서' 복잡한 구조 적용"],
        "remedy": "\"측정 먼저, 최적화 나중\" (Knuth, 1974). 프로파일러 기반 병목 식별 후 최적화",
        "reference": "Knuth, 'Structured Programming with go to Statements' (1974)",
    },
    "circular_dependency": {
        "name_ko": "순환 의존성",
        "severity": "심각",
        "description": "모듈 A→B→C→A 순환 참조. 빌드/테스트/배포 불가능",
        "symptoms": ["import 순서에 따라 에러 발생", "하나의 모듈 변경이 전체 재빌드 유발", "모듈 단위 테스트 불가능"],
        "remedy": "의존성 역전 원칙(DIP) + 인터페이스 추출 + 매개 모듈 도입",
        "reference": "Martin, 'Clean Architecture' (2017), Ch.14",
    },
}

# ══════════════════════════════════════════════════════════════════════
#  SOLID 원칙 (Robert C. Martin, 2000~2017)
# ══════════════════════════════════════════════════════════════════════

_SOLID_PRINCIPLES: dict[str, dict[str, Any]] = {
    "SRP": {
        "name_ko": "단일 책임 원칙",
        "name_en": "Single Responsibility Principle",
        "definition": "클래스는 변경의 이유가 단 하나여야 한다",
        "violation_signals": [
            "하나의 파일이 500줄 이상",
            "클래스명에 Manager/Handler/Processor 등 범용 이름 사용",
            "하나의 클래스가 DB + 비즈니스 로직 + UI 처리를 모두 수행",
        ],
        "metric": "클래스당 메서드 수 (이상적: ≤7), 파일 줄 수 (이상적: ≤300)",
        "reference": "Martin, 'Agile Software Development' (2002), Ch.8",
    },
    "OCP": {
        "name_ko": "개방-폐쇄 원칙",
        "name_en": "Open-Closed Principle",
        "definition": "확장에는 열려있고, 수정에는 닫혀있어야 한다",
        "violation_signals": [
            "새 기능 추가 시 기존 코드의 if/switch 분기를 매번 수정",
            "새 타입 추가 시 여러 파일을 동시에 변경해야 함",
            "플러그인/확장 포인트가 없는 경직된 구조",
        ],
        "metric": "새 기능 추가 시 기존 코드 변경 파일 수 (이상적: 0~1)",
        "reference": "Meyer, 'Object-Oriented Software Construction' (1988); Martin (2002)",
    },
    "LSP": {
        "name_ko": "리스코프 치환 원칙",
        "name_en": "Liskov Substitution Principle",
        "definition": "하위 타입은 상위 타입을 대체할 수 있어야 한다",
        "violation_signals": [
            "상속받은 메서드에서 NotImplementedError 던지기",
            "isinstance() 체크 후 분기하는 코드",
            "자식 클래스가 부모 계약을 위반 (직사각형-정사각형 문제)",
        ],
        "metric": "isinstance/type 체크 빈도 (이상적: 0, 다형성 사용)",
        "reference": "Liskov & Wing, 'A Behavioral Notion of Subtyping' (1994)",
    },
    "ISP": {
        "name_ko": "인터페이스 분리 원칙",
        "name_en": "Interface Segregation Principle",
        "definition": "클라이언트는 자신이 사용하지 않는 메서드에 의존하지 않아야 한다",
        "violation_signals": [
            "하나의 인터페이스/추상 클래스에 10개 이상 메서드",
            "구현 클래스에서 절반 이상의 메서드가 pass/stub",
            "하나의 변경이 무관한 클라이언트까지 재컴파일 유발",
        ],
        "metric": "인터페이스당 메서드 수 (이상적: ≤5), stub 메서드 비율 (이상적: 0%)",
        "reference": "Martin, 'Agile Software Development' (2002), Ch.12",
    },
    "DIP": {
        "name_ko": "의존성 역전 원칙",
        "name_en": "Dependency Inversion Principle",
        "definition": "상위 모듈은 하위 모듈에 의존하지 않고, 둘 다 추상화에 의존해야 한다",
        "violation_signals": [
            "비즈니스 로직에서 구체적 DB 라이브러리 직접 import",
            "고수준 모듈이 저수준 모듈의 구체 클래스를 직접 생성",
            "DI 컨테이너 없이 하드코딩된 의존성",
        ],
        "metric": "추상화 의존 비율 (이상적: 상위 모듈의 import 중 ≥80%가 인터페이스)",
        "reference": "Martin, 'Clean Architecture' (2017), Ch.11",
    },
}

# ══════════════════════════════════════════════════════════════════════
#  결합도 등급 기준 (Martin, 2017; Pressman, 2014)
# ══════════════════════════════════════════════════════════════════════

_COUPLING_GRADES: dict[str, dict[str, str]] = {
    "A": {"range": "Ca ≤ 3, Ce ≤ 3, I ∈ [0.3, 0.7]", "label": "최적 (Optimal)", "desc": "균형 잡힌 의존성, 안정적이면서 유연"},
    "B": {"range": "Ca ≤ 6, Ce ≤ 6, I ∈ [0.2, 0.8]", "label": "양호 (Good)", "desc": "관리 가능한 수준의 결합도"},
    "C": {"range": "Ca ≤ 10, Ce ≤ 10", "label": "주의 (Warning)", "desc": "결합도 증가 추세, 리팩토링 권장"},
    "D": {"range": "Ca > 10 or Ce > 10", "label": "위험 (Critical)", "desc": "과도한 결합, 변경 시 대규모 파급 효과"},
}

# ══════════════════════════════════════════════════════════════════════
#  DDD 전략/전술 패턴 (Eric Evans, 2003; Vaughn Vernon, 2013)
# ══════════════════════════════════════════════════════════════════════

_DDD_STRATEGIC_PATTERNS: list[dict[str, str]] = [
    {"name": "Bounded Context", "name_ko": "바운디드 컨텍스트", "desc": "도메인 모델의 적용 범위를 명확히 구분하는 경계"},
    {"name": "Ubiquitous Language", "name_ko": "유비쿼터스 언어", "desc": "팀 전체가 공유하는 도메인 용어 체계"},
    {"name": "Context Map", "name_ko": "컨텍스트 맵", "desc": "바운디드 컨텍스트 간 관계를 시각화한 다이어그램"},
    {"name": "Domain Event", "name_ko": "도메인 이벤트", "desc": "도메인에서 발생한 의미 있는 사건을 객체로 표현"},
]

_DDD_TACTICAL_PATTERNS: list[dict[str, str]] = [
    {"name": "Entity", "name_ko": "엔티티", "desc": "고유 식별자로 구분되는 도메인 객체 (생명주기 있음)"},
    {"name": "Value Object", "name_ko": "값 객체", "desc": "속성 값으로 동등성을 판단하는 불변 객체"},
    {"name": "Aggregate", "name_ko": "애그리거트", "desc": "일관성 경계를 형성하는 엔티티+값 객체 클러스터"},
    {"name": "Repository", "name_ko": "리포지토리", "desc": "애그리거트의 영속화를 추상화하는 인터페이스"},
    {"name": "Domain Service", "name_ko": "도메인 서비스", "desc": "특정 엔티티에 속하지 않는 도메인 로직"},
    {"name": "Application Service", "name_ko": "애플리케이션 서비스", "desc": "유스케이스 조율, 도메인 객체 간 협력 조정"},
]

# ══════════════════════════════════════════════════════════════════════
#  마이그레이션 전략 (Fowler, 2004; Newman, 2021)
# ══════════════════════════════════════════════════════════════════════

_MIGRATION_STRATEGIES: dict[str, dict[str, Any]] = {
    "strangler_fig": {
        "name_ko": "스트랭글러 무화과 패턴",
        "name_en": "Strangler Fig Pattern",
        "description": "기존 시스템을 점진적으로 새 시스템으로 교체. 구 시스템 위에 새 시스템이 자라남",
        "risk": "낮음",
        "duration": "6~24개월",
        "best_for": "모놀리스→마이크로서비스 전환",
        "reference": "Fowler (2004)",
    },
    "branch_by_abstraction": {
        "name_ko": "추상화 브랜칭",
        "name_en": "Branch by Abstraction",
        "description": "인터페이스 추출 → 새 구현 작성 → 스위칭. 코드베이스 내에서 점진 전환",
        "risk": "낮음",
        "duration": "2~6개월",
        "best_for": "라이브러리/프레임워크 교체",
        "reference": "Fowler (2014)",
    },
    "parallel_run": {
        "name_ko": "병렬 실행",
        "name_en": "Parallel Run",
        "description": "신/구 시스템을 동시에 실행하여 결과를 비교 검증 후 전환",
        "risk": "매우 낮음",
        "duration": "3~12개월",
        "best_for": "금융/결제 등 정확성이 중요한 시스템",
        "reference": "Fowler, 'Parallel Change' (2014)",
    },
    "big_bang": {
        "name_ko": "빅뱅 전환",
        "name_en": "Big Bang Migration",
        "description": "특정 시점에 한번에 전체 전환. 빠르지만 위험도 높음",
        "risk": "매우 높음",
        "duration": "1~3개월",
        "best_for": "소규모 시스템, 다운타임 허용 가능 시",
        "reference": "Newman, 'Monolith to Microservices' (2019)",
    },
    "cqrs_event_sourcing": {
        "name_ko": "CQRS + 이벤트 소싱 도입",
        "name_en": "CQRS + Event Sourcing",
        "description": "읽기/쓰기 모델 분리 + 모든 상태 변경을 이벤트로 저장",
        "risk": "보통",
        "duration": "6~18개월",
        "best_for": "복잡한 도메인, 감사(Audit) 요구사항, 이벤트 기반 전환",
        "reference": "Young (2010); Fowler (2011)",
    },
}


class ArchitectureEvaluatorTool(BaseTool):
    """소프트웨어 아키텍처 평가 도구 (교수급)

    ISO/IEC 25010:2023 품질모델 기반으로 소프트웨어 아키텍처를 8개 관점에서
    종합 진단합니다. SOLID 원칙, GoF 디자인 패턴, 안티패턴 탐지,
    결합도/응집도 정량화, DDD 분석, 마이그레이션 전략까지 교수급 리포트를 생성합니다.

    학술 근거:
      - ISO/IEC 25010:2023, Robert C. Martin (2017), Eric Evans (2003),
        Martin Fowler (2002), GoF (1994), Bass/Clements/Kazman (2021)
    """

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "evaluate")
        actions = {
            "evaluate": self._evaluate,
            "solid": self._solid_analysis,
            "patterns": self._patterns_analysis,
            "antipatterns": self._antipatterns_detect,
            "coupling": self._coupling_analysis,
            "migration": self._migration_strategy,
            "ddd": self._ddd_analysis,
            "full": self._full_report,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return (
            f"알 수 없는 action: {action}. "
            "evaluate, solid, patterns, antipatterns, coupling, migration, ddd, full 중 하나를 사용하세요."
        )

    # ══════════════════════════════════════════════════════════════
    #  1. evaluate — ISO/IEC 25010 기반 아키텍처 종합 평가
    # ══════════════════════════════════════════════════════════════

    async def _evaluate(self, p: dict) -> str:
        system_desc = p.get("system_description", "")
        architecture = p.get("architecture", "")
        codebase = p.get("codebase_summary", "")

        # ISO 25010 품질 특성 표 생성
        lines = [
            "## ISO/IEC 25010:2023 아키텍처 품질 평가",
            "",
            f"**평가 대상**: {system_desc or '미지정'}",
            f"**아키텍처**: {architecture or '미지정'}",
            "",
            "### 8대 품질 특성 평가 프레임워크",
            "",
            "| 품질 특성 | 영문명 | 가중치 | 하위 특성 | 평가 기준 |",
            "|----------|--------|--------|----------|----------|",
        ]
        for key, q in _ISO25010_QUALITIES.items():
            sub = ", ".join(q["sub_chars"])
            criteria = "; ".join(q["evaluation_criteria"][:2])
            lines.append(
                f"| {q['name_ko']} | {q['name_en']} | x{q['weight']} | {sub} | {criteria} |"
            )

        lines.extend([
            "",
            "### 가중치 기준 (Bass, Clements & Kazman, 2021)",
            "- 보안(1.3), 유지보수성(1.3): 장기 프로젝트에서 가장 영향이 큰 품질 속성",
            "- 기능적합성(1.2), 신뢰성(1.2): 시스템의 핵심 존재 이유",
            "- 성능효율성(1.1): 사용자 경험 직결",
            "- 호환성(0.9), 사용성(0.8), 이식성(0.8): 상황에 따라 중요도 변동",
        ])

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 소프트웨어 아키텍처 교수이자 ISO/IEC 25010:2023 인증 심사원입니다.\n"
                "다음 시스템의 아키텍처를 ISO/IEC 25010 품질모델의 8대 특성으로 평가하세요.\n\n"
                "각 품질 특성에 대해:\n"
                "1. **현재 수준 평가** (A/B/C/D/F 등급 + 점수 0~100)\n"
                "2. **근거** — 왜 이 등급인지 구체적 이유\n"
                "3. **개선 권고** — 한 단계 올리려면 무엇을 해야 하는지\n"
                "4. **가중 점수** — 점수 × 가중치\n\n"
                "마지막에 가중 종합 점수(0~100)와 전체 등급을 산출하세요.\n"
                "한국어로, 비개발자(CEO)도 핵심을 이해할 수 있도록 설명하세요.\n"
                "학술 근거를 반드시 인용하세요."
            ),
            user_prompt=(
                f"시스템 설명: {system_desc}\n"
                f"아키텍처: {architecture}\n"
                f"코드베이스 요약: {codebase}\n\n"
                f"평가 프레임워크:\n{formatted}"
            ),
        )

        return f"{formatted}\n\n---\n\n## 전문가 평가 결과\n\n{analysis}"

    # ══════════════════════════════════════════════════════════════
    #  2. solid — SOLID 원칙 준수도 분석
    # ══════════════════════════════════════════════════════════════

    async def _solid_analysis(self, p: dict) -> str:
        codebase = p.get("codebase_summary", "")
        code_sample = p.get("code_sample", "")

        lines = [
            "## SOLID 원칙 준수도 분석",
            "",
            "### Robert C. Martin의 SOLID 5원칙 (Clean Architecture, 2017)",
            "",
            "| 원칙 | 영문 | 정의 | 위반 시그널 | 정량 지표 |",
            "|------|------|------|-----------|----------|",
        ]
        for key, principle in _SOLID_PRINCIPLES.items():
            signals = "; ".join(principle["violation_signals"][:2])
            lines.append(
                f"| **{key}** — {principle['name_ko']} | {principle['name_en']} "
                f"| {principle['definition']} | {signals} | {principle['metric']} |"
            )

        lines.extend([
            "",
            "### 원칙별 상세 위반 패턴",
            "",
        ])
        for key, principle in _SOLID_PRINCIPLES.items():
            lines.append(f"#### {key}: {principle['name_ko']} ({principle['name_en']})")
            lines.append(f"- **정의**: {principle['definition']}")
            lines.append(f"- **학술 근거**: {principle['reference']}")
            lines.append("- **위반 징후**:")
            for signal in principle["violation_signals"]:
                lines.append(f"  - {signal}")
            lines.append(f"- **정량 지표**: {principle['metric']}")
            lines.append("")

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 Robert C. Martin의 Clean Architecture 원칙에 정통한 소프트웨어 설계 교수입니다.\n"
                "아래 코드/시스템의 SOLID 5원칙 준수도를 분석하세요.\n\n"
                "각 원칙별로:\n"
                "1. **준수도 점수** (0~100점)\n"
                "2. **위반 사례 탐지** — 구체적 코드/모듈 지목\n"
                "3. **개선 코드 예시** — Before/After 비교\n"
                "4. **우선순위** — 어떤 원칙부터 개선해야 하는지\n\n"
                "종합 SOLID 점수(0~100)와 등급(A/B/C/D/F)을 산출하세요.\n"
                "한국어로 답변하되 학술 근거를 반드시 포함하세요."
            ),
            user_prompt=(
                f"코드베이스 설명: {codebase}\n"
                f"코드 샘플:\n```\n{code_sample}\n```\n\n"
                f"평가 기준:\n{formatted}"
            ),
        )

        return f"{formatted}\n\n---\n\n## SOLID 분석 결과\n\n{analysis}"

    # ══════════════════════════════════════════════════════════════
    #  3. patterns — GoF 디자인 패턴 적합성 분석
    # ══════════════════════════════════════════════════════════════

    async def _patterns_analysis(self, p: dict) -> str:
        system_desc = p.get("system_description", "")
        requirements = p.get("requirements", "")
        current_patterns = p.get("current_patterns", "")

        # 아키텍처 패턴 표
        lines = [
            "## 디자인 패턴 적합성 분석",
            "",
            "### 아키텍처 패턴 비교 (Richards & Ford, 2020)",
            "",
            "| 패턴 | 장점 | 단점 | 적합 상황 | 추천도 |",
            "|------|------|------|----------|--------|",
        ]
        for key, pat in _ARCHITECTURE_PATTERNS.items():
            stars = "★" * pat["star_rating"] + "☆" * (5 - pat["star_rating"])
            pros = ", ".join(pat["pros"][:2])
            cons = ", ".join(pat["cons"][:2])
            lines.append(
                f"| {pat['name_ko']} | {pros} | {cons} | {pat['best_for'][:30]}... | {stars} |"
            )

        lines.extend([
            "",
            "### GoF 23 디자인 패턴 카테고리",
            "",
            "**생성 패턴 (Creational)**: Abstract Factory, Builder, Factory Method, Prototype, Singleton",
            "**구조 패턴 (Structural)**: Adapter, Bridge, Composite, Decorator, Facade, Flyweight, Proxy",
            "**행동 패턴 (Behavioral)**: Chain of Responsibility, Command, Interpreter, Iterator, "
            "Mediator, Memento, Observer, State, Strategy, Template Method, Visitor",
            "",
            "*출처: Gamma, Helm, Johnson & Vlissides, 'Design Patterns' (1994)*",
        ])

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 GoF 디자인 패턴과 아키텍처 패턴에 정통한 소프트웨어 설계 교수입니다.\n"
                "아래 시스템에 적합한 디자인 패턴과 아키텍처 패턴을 분석하세요.\n\n"
                "분석 항목:\n"
                "1. **현재 사용 중인 패턴 평가** — 적합한지, 잘못 적용된 것은 없는지\n"
                "2. **추천 아키텍처 패턴** — 시스템 특성에 맞는 최적 아키텍처 (근거 포함)\n"
                "3. **추천 GoF 패턴** — 적용 가능한 패턴 5가지 + 적용 위치/이유\n"
                "4. **패턴 조합 전략** — 여러 패턴의 시너지 효과\n"
                "5. **과잉 설계 경고** — 불필요한 패턴 적용 방지\n\n"
                "한국어로, 구체적 코드 예시를 포함하여 답변하세요.\n"
                "각 추천에 학술 근거를 인용하세요."
            ),
            user_prompt=(
                f"시스템 설명: {system_desc}\n"
                f"요구사항: {requirements}\n"
                f"현재 사용 중인 패턴: {current_patterns}\n\n"
                f"참고 데이터:\n{formatted}"
            ),
        )

        return f"{formatted}\n\n---\n\n## 패턴 분석 결과\n\n{analysis}"

    # ══════════════════════════════════════════════════════════════
    #  4. antipatterns — 안티패턴 탐지
    # ══════════════════════════════════════════════════════════════

    async def _antipatterns_detect(self, p: dict) -> str:
        codebase = p.get("codebase_summary", "")
        code_sample = p.get("code_sample", "")
        symptoms = p.get("symptoms", "")

        lines = [
            "## 안티패턴 탐지 보고서",
            "",
            "### 주요 안티패턴 목록 (Brown et al., 1998; Fowler, 2002)",
            "",
            "| 안티패턴 | 심각도 | 핵심 증상 | 치료법 |",
            "|----------|--------|----------|--------|",
        ]
        for key, ap in _ANTIPATTERNS.items():
            symptom_summary = "; ".join(ap["symptoms"][:2])
            lines.append(
                f"| {ap['name_ko']} | **{ap['severity']}** | {symptom_summary} | {ap['remedy'][:40]}... |"
            )

        lines.extend([
            "",
            "### 안티패턴 상세 진단 기준",
            "",
        ])
        for key, ap in _ANTIPATTERNS.items():
            lines.append(f"#### {ap['name_ko']}")
            lines.append(f"- **심각도**: {ap['severity']}")
            lines.append(f"- **설명**: {ap['description']}")
            lines.append("- **증상**:")
            for symptom in ap["symptoms"]:
                lines.append(f"  - {symptom}")
            lines.append(f"- **치료법**: {ap['remedy']}")
            lines.append(f"- **참고 문헌**: {ap['reference']}")
            lines.append("")

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 레거시 시스템 리팩토링 전문 교수이자 소프트웨어 아키텍트입니다.\n"
                "아래 시스템에서 안티패턴을 탐지하고 치료 방안을 제시하세요.\n\n"
                "분석 항목:\n"
                "1. **탐지된 안티패턴 목록** — 근거와 함께 (증상 매칭)\n"
                "2. **심각도 순위** — 가장 위험한 것부터 정렬\n"
                "3. **연쇄 효과 분석** — 하나의 안티패턴이 다른 것을 유발하는 패턴\n"
                "4. **리팩토링 로드맵** — 단계별 치료 계획 (1주/1개월/3개월)\n"
                "5. **치료 전/후 코드 예시** — Before/After 비교\n"
                "6. **예방 문화 구축** — 안티패턴 재발 방지 프로세스\n\n"
                "한국어로, CEO도 위험성을 이해할 수 있도록 비유를 활용하세요.\n"
                "학술 근거를 반드시 인용하세요."
            ),
            user_prompt=(
                f"코드베이스 설명: {codebase}\n"
                f"증상/문제점: {symptoms}\n"
                f"코드 샘플:\n```\n{code_sample}\n```\n\n"
                f"안티패턴 진단 기준:\n{formatted}"
            ),
        )

        return f"{formatted}\n\n---\n\n## 안티패턴 탐지 결과\n\n{analysis}"

    # ══════════════════════════════════════════════════════════════
    #  5. coupling — 결합도/응집도 분석
    # ══════════════════════════════════════════════════════════════

    async def _coupling_analysis(self, p: dict) -> str:
        modules = p.get("modules", "")
        dependencies = p.get("dependencies", "")

        lines = [
            "## 결합도/응집도 분석 (Coupling & Cohesion)",
            "",
            "### 핵심 지표 정의 (Robert C. Martin, 2017)",
            "",
            "| 지표 | 영문 | 정의 | 이상적 범위 |",
            "|------|------|------|-----------|",
            "| Ca (구심 결합도) | Afferent Coupling | 이 모듈에 의존하는 외부 모듈 수 | ≤ 5 |",
            "| Ce (원심 결합도) | Efferent Coupling | 이 모듈이 의존하는 외부 모듈 수 | ≤ 5 |",
            "| I (불안정성) | Instability = Ce/(Ca+Ce) | 0(완전 안정)~1(완전 불안정) | 0.3~0.7 |",
            "| A (추상도) | Abstractness | 추상 타입 비율 | 패키지별 상이 |",
            "| D (주계열 이탈) | Distance from Main Sequence | |I+A-1| | ≤ 0.3 |",
            "",
            "### 결합도 등급 기준",
            "",
            "| 등급 | 조건 | 수준 | 설명 |",
            "|------|------|------|------|",
        ]
        for grade, info in _COUPLING_GRADES.items():
            lines.append(f"| **{grade}** | {info['range']} | {info['label']} | {info['desc']} |")

        lines.extend([
            "",
            "### 응집도 유형 (높은 순)",
            "",
            "| 유형 | 설명 | 등급 |",
            "|------|------|------|",
            "| 기능적 응집 (Functional) | 단일 기능 수행에 모든 요소가 기여 | 최고 |",
            "| 순차적 응집 (Sequential) | 한 요소의 출력이 다음 요소의 입력 | 높음 |",
            "| 통신적 응집 (Communicational) | 동일 데이터를 처리하는 요소들 | 중간 |",
            "| 절차적 응집 (Procedural) | 실행 순서에 의한 관계 | 낮음 |",
            "| 시간적 응집 (Temporal) | 같은 시점에 실행되는 것들 | 나쁨 |",
            "| 논리적 응집 (Logical) | 같은 카테고리이나 기능이 다름 | 나쁨 |",
            "| 우연적 응집 (Coincidental) | 아무 관계 없는 요소들 | 최악 |",
            "",
            "*출처: Pressman, 'Software Engineering: A Practitioner's Approach' (2014); Martin (2017)*",
        ])

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 소프트웨어 메트릭스와 아키텍처 분석 전문 교수입니다.\n"
                "Robert C. Martin의 패키지 결합도 이론과 Pressman의 응집도 분류를 기반으로\n"
                "아래 시스템의 결합도/응집도를 분석하세요.\n\n"
                "분석 항목:\n"
                "1. **모듈별 Ca/Ce/I 산출** — 구심 결합도, 원심 결합도, 불안정성 지수\n"
                "2. **주계열 분석** (Main Sequence) — 각 모듈이 Zone of Pain/Zone of Uselessness에 빠져 있지 않은지\n"
                "3. **응집도 유형 판별** — 각 모듈의 응집도 유형 (기능적~우연적)\n"
                "4. **순환 의존성 탐지** — 모듈 간 순환 참조 경로\n"
                "5. **의존성 그래프** — 모듈 간 의존 관계를 텍스트 다이어그램으로 시각화\n"
                "6. **리팩토링 권고** — 결합도를 낮추고 응집도를 높이는 구체적 방안\n\n"
                "모든 수치에 근거를 제시하고, 한국어로 답변하세요."
            ),
            user_prompt=(
                f"모듈 목록: {modules}\n"
                f"의존성 관계: {dependencies}\n\n"
                f"평가 기준:\n{formatted}"
            ),
        )

        return f"{formatted}\n\n---\n\n## 결합도/응집도 분석 결과\n\n{analysis}"

    # ══════════════════════════════════════════════════════════════
    #  6. migration — 아키텍처 마이그레이션 전략
    # ══════════════════════════════════════════════════════════════

    async def _migration_strategy(self, p: dict) -> str:
        current_arch = p.get("current_architecture", "")
        target_arch = p.get("target_architecture", "")
        constraints = p.get("constraints", "")
        team_size = p.get("team_size", "")

        lines = [
            "## 아키텍처 마이그레이션 전략",
            "",
            f"**현재**: {current_arch or '미지정'}",
            f"**목표**: {target_arch or '미지정'}",
            f"**제약 조건**: {constraints or '미지정'}",
            "",
            "### 마이그레이션 전략 비교 (Fowler, 2004; Newman, 2021)",
            "",
            "| 전략 | 위험도 | 기간 | 적합 상황 | 참고 |",
            "|------|--------|------|----------|------|",
        ]
        for key, strategy in _MIGRATION_STRATEGIES.items():
            lines.append(
                f"| {strategy['name_ko']} | {strategy['risk']} | {strategy['duration']} "
                f"| {strategy['best_for']} | {strategy['reference']} |"
            )

        lines.extend([
            "",
            "### 전략별 상세 설명",
            "",
        ])
        for key, strategy in _MIGRATION_STRATEGIES.items():
            lines.append(f"#### {strategy['name_ko']} ({strategy['name_en']})")
            lines.append(f"- {strategy['description']}")
            lines.append(f"- **위험도**: {strategy['risk']} | **소요 기간**: {strategy['duration']}")
            lines.append(f"- **적합 상황**: {strategy['best_for']}")
            lines.append("")

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 대규모 시스템 마이그레이션 경험이 풍부한 아키텍처 교수이자\n"
                "기술 전략 컨설턴트입니다. Fowler, Newman의 마이그레이션 패턴을 기반으로\n"
                "아래 시스템의 최적 마이그레이션 전략을 수립하세요.\n\n"
                "분석 항목:\n"
                "1. **현재 아키텍처 진단** — 마이그레이션이 필요한 근본 원인\n"
                "2. **최적 전략 추천** — 근거와 함께 가장 적합한 전략 선택\n"
                "3. **단계별 로드맵** — 3개월/6개월/12개월 마일스톤\n"
                "4. **리스크 분석** — 각 단계의 위험 요소와 완화 방안\n"
                "5. **팀 구성 및 역할** — 마이그레이션에 필요한 인력과 역할\n"
                "6. **롤백 전략** — 실패 시 복구 방안\n"
                "7. **비용-효과 분석** — 마이그레이션 투자 대비 기대 효과\n\n"
                "한국어로, CEO가 의사결정할 수 있도록 비즈니스 관점도 포함하세요.\n"
                "학술 근거를 반드시 인용하세요."
            ),
            user_prompt=(
                f"현재 아키텍처: {current_arch}\n"
                f"목표 아키텍처: {target_arch}\n"
                f"제약 조건: {constraints}\n"
                f"팀 규모: {team_size}\n\n"
                f"전략 옵션:\n{formatted}"
            ),
        )

        return f"{formatted}\n\n---\n\n## 마이그레이션 전략 분석 결과\n\n{analysis}"

    # ══════════════════════════════════════════════════════════════
    #  7. ddd — DDD 도메인 주도 설계 분석
    # ══════════════════════════════════════════════════════════════

    async def _ddd_analysis(self, p: dict) -> str:
        domain_desc = p.get("domain_description", "")
        bounded_contexts = p.get("bounded_contexts", "")
        business_rules = p.get("business_rules", "")

        lines = [
            "## DDD 도메인 주도 설계 분석",
            "",
            "### 전략적 설계 패턴 (Eric Evans, 2003)",
            "",
            "| 패턴 | 한국어 | 설명 |",
            "|------|--------|------|",
        ]
        for pat in _DDD_STRATEGIC_PATTERNS:
            lines.append(f"| {pat['name']} | {pat['name_ko']} | {pat['desc']} |")

        lines.extend([
            "",
            "### 전술적 설계 패턴 (Evans 2003; Vernon 2013)",
            "",
            "| 패턴 | 한국어 | 설명 |",
            "|------|--------|------|",
        ])
        for pat in _DDD_TACTICAL_PATTERNS:
            lines.append(f"| {pat['name']} | {pat['name_ko']} | {pat['desc']} |")

        lines.extend([
            "",
            "### 바운디드 컨텍스트 간 관계 유형 (Context Mapping)",
            "",
            "| 관계 | 설명 |",
            "|------|------|",
            "| Shared Kernel | 두 컨텍스트가 도메인 모델 일부를 공유 |",
            "| Customer-Supplier | 공급자가 소비자의 요구에 맞춰 API 제공 |",
            "| Conformist | 하류 컨텍스트가 상류 모델을 그대로 수용 |",
            "| Anti-Corruption Layer | 외부 모델의 오염을 방지하는 변환 레이어 |",
            "| Open Host Service | 범용 프로토콜로 여러 소비자에게 서비스 |",
            "| Published Language | 표준화된 교환 형식 (JSON Schema, Protobuf 등) |",
            "| Separate Ways | 통합하지 않고 독립 운영 |",
            "",
            "*출처: Evans (2003), Ch.14; Vernon, 'Implementing Domain-Driven Design' (2013)*",
        ])

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 Eric Evans의 DDD에 정통한 소프트웨어 아키텍처 교수입니다.\n"
                "아래 도메인을 DDD 관점에서 분석하고 설계를 제안하세요.\n\n"
                "분석 항목:\n"
                "1. **핵심 도메인 식별** — Core Domain / Supporting / Generic 분류\n"
                "2. **유비쿼터스 언어 정의** — 도메인 용어 사전 (영문-한국어 매핑)\n"
                "3. **바운디드 컨텍스트 도출** — 경계와 책임 정의\n"
                "4. **컨텍스트 맵** — 컨텍스트 간 관계 유형 매핑\n"
                "5. **애그리거트 설계** — 루트 엔티티, 값 객체, 불변식 정의\n"
                "6. **도메인 이벤트 설계** — 핵심 비즈니스 이벤트 목록\n"
                "7. **Anti-Corruption Layer 필요성** — 외부 시스템과의 경계\n"
                "8. **DDD 적용 수준 평가** — 현재 코드가 DDD를 얼마나 따르는지 (0~100)\n\n"
                "한국어로, 비개발자도 핵심 개념을 이해할 수 있도록 비유를 활용하세요.\n"
                "Evans (2003), Vernon (2013) 학술 근거를 인용하세요."
            ),
            user_prompt=(
                f"도메인 설명: {domain_desc}\n"
                f"바운디드 컨텍스트 (현재): {bounded_contexts}\n"
                f"비즈니스 규칙: {business_rules}\n\n"
                f"DDD 패턴 참조:\n{formatted}"
            ),
        )

        return f"{formatted}\n\n---\n\n## DDD 분석 결과\n\n{analysis}"

    # ══════════════════════════════════════════════════════════════
    #  8. full — 전체 종합 리포트 (asyncio.gather 병렬)
    # ══════════════════════════════════════════════════════════════

    async def _full_report(self, p: dict) -> str:
        # 7개 분석을 asyncio.gather로 병렬 실행
        results = await asyncio.gather(
            self._evaluate(p),
            self._solid_analysis(p),
            self._patterns_analysis(p),
            self._antipatterns_detect(p),
            self._coupling_analysis(p),
            self._migration_strategy(p),
            self._ddd_analysis(p),
            return_exceptions=True,
        )

        labels = [
            "1. ISO/IEC 25010 아키텍처 품질 평가",
            "2. SOLID 원칙 준수도 분석",
            "3. 디자인 패턴 적합성 분석",
            "4. 안티패턴 탐지",
            "5. 결합도/응집도 분석",
            "6. 아키텍처 마이그레이션 전략",
            "7. DDD 도메인 주도 설계 분석",
        ]

        sections = [
            "# 소프트웨어 아키텍처 종합 평가 보고서",
            "",
            "**평가 프레임워크**: ISO/IEC 25010:2023, Clean Architecture, GoF, DDD",
            "**분석 관점**: 7가지 (품질 특성, SOLID, 패턴, 안티패턴, 결합도, 마이그레이션, DDD)",
            "",
            "---",
            "",
        ]

        for i, (label, result) in enumerate(zip(labels, results)):
            sections.append(f"## {label}")
            sections.append("")
            if isinstance(result, Exception):
                sections.append(f"분석 중 오류 발생: {str(result)}")
                logger.error("아키텍처 평가 섹션 %d 오류: %s", i, result)
            else:
                sections.append(result)
            sections.append("")
            sections.append("---")
            sections.append("")

        sections.extend([
            "## 학술 참고 문헌",
            "",
            "| 번호 | 저자 | 제목 | 연도 |",
            "|------|------|------|------|",
            "| 1 | ISO/IEC JTC 1/SC 7 | ISO/IEC 25010:2023 — Systems and Software Quality | 2023 |",
            "| 2 | Robert C. Martin | Clean Architecture | 2017 |",
            "| 3 | Eric Evans | Domain-Driven Design | 2003 |",
            "| 4 | Martin Fowler | Patterns of Enterprise Application Architecture | 2002 |",
            "| 5 | Gamma, Helm, Johnson, Vlissides | Design Patterns (GoF) | 1994 |",
            "| 6 | Bass, Clements, Kazman | Software Architecture in Practice (4th) | 2021 |",
            "| 7 | Richards & Ford | Fundamentals of Software Architecture | 2020 |",
            "| 8 | Sam Newman | Building Microservices (2nd) | 2021 |",
            "| 9 | Vaughn Vernon | Implementing Domain-Driven Design | 2013 |",
            "| 10 | Brown, Malveau, McCormick, Mowbray | AntiPatterns | 1998 |",
        ])

        return "\n".join(sections)
