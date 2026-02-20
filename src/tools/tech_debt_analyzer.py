"""
기술부채 분석 도구 (Technical Debt Analyzer) — 코드베이스의 기술부채를 과학적으로 측정하고
상환 전략을 수립합니다.

SQALE 방법론 + Martin Fowler의 Quadrant + WSJF 우선순위 기법을 결합하여
기술부채의 유형 분류, 비즈니스 영향도 평가, 상환 로드맵까지 일관된 프레임워크를 제공합니다.

학술 근거:
  - Ward Cunningham, "The WyCash Portfolio Management System" (OOPSLA 1992)
    — '기술부채(Technical Debt)' 개념 최초 제안. 의도적 설계 타협을 금융 부채에 비유
  - Martin Fowler, "Refactoring: Improving the Design of Existing Code" (2nd ed., 2018)
    — 22가지 코드 스멜 분류 체계 및 리팩토링 카탈로그
  - Martin Fowler, "Technical Debt Quadrant" (2009)
    — 의도적/무의식 × 신중/무모 2x2 매트릭스로 부채 성격 분류
  - Jean-Louis Letouzey, "The SQALE Method" (2012)
    — Software Quality Assessment based on Lifecycle Expectations.
      8가지 품질 특성 기반 기술부채 정량화 방법론
  - SAFe (Scaled Agile Framework) — WSJF (Weighted Shortest Job First)
    — Cost of Delay / Job Duration 으로 상환 우선순위 결정

사용 방법:
  - action="assess"     : 기술부채 종합 평가 (SQALE 방법론)
  - action="classify"   : 부채 유형 분류 (Fowler's Quadrant: 의도적/무의식 x 신중/무로)
  - action="smells"     : 코드 스멜 탐지 (Martin Fowler 22가지 카탈로그)
  - action="impact"     : 비즈니스 영향도 분석 (개발 속도/안정성/채용)
  - action="prioritize" : 상환 우선순위 결정 (WSJF: Weighted Shortest Job First)
  - action="roadmap"    : 상환 로드맵 생성 (Sprint 단위 계획)
  - action="metrics"    : 기술부채 측정 지표 (Debt Ratio, Coverage, Complexity)
  - action="full"       : 전체 종합 리포트 (병렬 실행)

필요 환경변수: 없음 (AI 분석은 _llm_call 사용)
필요 라이브러리: 없음 (표준 라이브러리만 사용)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.tech_debt_analyzer")

# ─── 기술부채 유형 분류 (Cunningham 1992 + 실무 확장) ──────────────

_DEBT_TYPES: dict[str, dict] = {
    "code": {
        "name": "코드 부채",
        "desc": "중복 코드, 복잡한 조건문, 매직 넘버, 네이밍 불량 등",
        "examples": ["중복 코드 (DRY 위반)", "과도한 조건 분기", "매직 넘버/스트링", "일관성 없는 네이밍"],
        "severity_weight": 0.8,
        "fix_effort": "낮음~중간",
    },
    "design": {
        "name": "설계 부채",
        "desc": "SOLID 원칙 위반, 순환 의존성, God Object, 레이어 침범",
        "examples": ["God Class/Object", "순환 의존성", "SOLID 원칙 위반", "잘못된 추상화 수준"],
        "severity_weight": 1.0,
        "fix_effort": "중간~높음",
    },
    "documentation": {
        "name": "문서 부채",
        "desc": "누락된 API 문서, 오래된 README, 주석-코드 불일치",
        "examples": ["API 문서 부재", "오래된 README", "주석과 코드 불일치", "아키텍처 결정 기록(ADR) 부재"],
        "severity_weight": 0.5,
        "fix_effort": "낮음",
    },
    "test": {
        "name": "테스트 부채",
        "desc": "낮은 코드 커버리지, 깨진 테스트, 통합 테스트 부재",
        "examples": ["낮은 코드 커버리지 (<60%)", "깨진/무시된 테스트", "통합 테스트 부재", "테스트 데이터 하드코딩"],
        "severity_weight": 0.9,
        "fix_effort": "중간",
    },
    "infrastructure": {
        "name": "인프라 부채",
        "desc": "수동 배포, 모니터링 부재, 보안 패치 지연, CI/CD 미흡",
        "examples": ["수동 배포 프로세스", "모니터링/알림 부재", "보안 패치 지연", "CI/CD 파이프라인 미흡"],
        "severity_weight": 0.85,
        "fix_effort": "중간~높음",
    },
    "dependency": {
        "name": "의존성 부채",
        "desc": "오래된 라이브러리, EOL 런타임, 버전 충돌, 미사용 의존성",
        "examples": ["메이저 버전 2+ 뒤처진 라이브러리", "EOL 런타임/프레임워크", "버전 충돌/호환성 문제", "미사용 의존성 방치"],
        "severity_weight": 0.7,
        "fix_effort": "낮음~중간",
    },
}

# ─── Martin Fowler 코드 스멜 카탈로그 (Refactoring 2nd ed., 2018) ────

_CODE_SMELLS: dict[str, dict] = {
    "long_method": {
        "name": "Long Method (긴 메서드)",
        "desc": "한 메서드가 너무 많은 일을 함. 일반적으로 20줄 초과 시 의심",
        "threshold": "20줄 초과",
        "refactoring": "Extract Method, Decompose Conditional",
        "severity": "높음",
    },
    "large_class": {
        "name": "Large Class (거대한 클래스)",
        "desc": "클래스가 너무 많은 책임을 가짐. SRP(단일 책임 원칙) 위반",
        "threshold": "300줄 초과 또는 필드 15개 초과",
        "refactoring": "Extract Class, Extract Subclass",
        "severity": "높음",
    },
    "feature_envy": {
        "name": "Feature Envy (기능 편애)",
        "desc": "메서드가 자기 클래스보다 다른 클래스의 데이터를 더 많이 사용",
        "threshold": "외부 클래스 참조가 내부 참조의 2배 초과",
        "refactoring": "Move Method, Extract Method",
        "severity": "중간",
    },
    "data_clumps": {
        "name": "Data Clumps (데이터 뭉치)",
        "desc": "항상 함께 다니는 데이터 그룹이 별도 객체로 추출되지 않음",
        "threshold": "3개 이상 파라미터가 3곳 이상에서 반복",
        "refactoring": "Extract Class, Introduce Parameter Object",
        "severity": "중간",
    },
    "primitive_obsession": {
        "name": "Primitive Obsession (기본형 집착)",
        "desc": "도메인 개념을 기본형(str, int)으로만 표현. 타입 안전성 저하",
        "threshold": "도메인 개념이 str/int로 3곳 이상 반복",
        "refactoring": "Replace Primitive with Object, Replace Type Code with Subclass",
        "severity": "중간",
    },
    "switch_statements": {
        "name": "Switch Statements (조건문 남용)",
        "desc": "동일 조건 분기가 여러 곳에 반복. 다형성으로 대체 가능",
        "threshold": "동일 switch/if-elif 패턴 2곳 이상",
        "refactoring": "Replace Conditional with Polymorphism, Strategy Pattern",
        "severity": "중간",
    },
    "divergent_change": {
        "name": "Divergent Change (산탄총 수술의 반대)",
        "desc": "하나의 클래스가 서로 다른 이유로 자주 변경됨",
        "threshold": "최근 10커밋에서 3가지 이상 다른 이유로 변경",
        "refactoring": "Extract Class — 변경 이유별로 분리",
        "severity": "높음",
    },
    "shotgun_surgery": {
        "name": "Shotgun Surgery (산탄총 수술)",
        "desc": "하나의 변경이 여러 클래스를 동시에 수정해야 함",
        "threshold": "단일 변경에 5개 이상 파일 수정 필요",
        "refactoring": "Move Method, Move Field, Inline Class",
        "severity": "높음",
    },
    "parallel_inheritance": {
        "name": "Parallel Inheritance Hierarchies (병렬 상속)",
        "desc": "한 클래스의 서브클래스 추가 시 다른 계층에도 추가 필요",
        "threshold": "두 상속 계층이 1:1 대응",
        "refactoring": "Move Method/Field — 한쪽 계층 제거", "severity": "중간",
    },
    "speculative_generality": {
        "name": "Speculative Generality (추측성 일반화)",
        "desc": "'나중에 필요할 것 같아서' 만든 불필요한 추상화",
        "threshold": "사용처 1곳 이하인 추상 클래스/인터페이스",
        "refactoring": "Collapse Hierarchy, Inline Class", "severity": "낮음",
    },
    "dead_code": {
        "name": "Dead Code (죽은 코드)",
        "desc": "실행되지 않는 코드, 미사용 변수/함수/import",
        "threshold": "호출자가 0인 함수, 미사용 import",
        "refactoring": "Remove Dead Code", "severity": "낮음",
    },
    "god_object": {
        "name": "God Object (신 객체)",
        "desc": "시스템의 모든 것을 알고 모든 것을 하는 거대한 객체",
        "threshold": "500줄+ / 20메서드+ / 10의존성+",
        "refactoring": "Extract Class 반복, Facade Pattern", "severity": "치명적",
    },
    "middle_man": {
        "name": "Middle Man (중개인)",
        "desc": "대부분의 메서드를 다른 클래스에 위임만 함",
        "threshold": "메서드의 50% 이상이 단순 위임",
        "refactoring": "Remove Middle Man, Inline Method", "severity": "낮음",
    },
}

# ─── SQALE 품질 특성 (Letouzey, 2012) ──────────────────────────

_SQALE_CHARACTERISTICS: dict[str, dict] = {
    "testability": {
        "name": "테스트 용이성", "desc": "소프트웨어를 테스트하기 쉬운 정도",
        "indicators": ["단위 테스트 커버리지", "테스트 격리도", "Mocking 필요 수준"],
        "remediation_weight": 1.0,
    },
    "reliability": {
        "name": "신뢰성", "desc": "의도한 기능을 안정적으로 수행하는 정도",
        "indicators": ["에러 핸들링 품질", "경합 조건 유무", "복구 메커니즘"],
        "remediation_weight": 1.2,
    },
    "changeability": {
        "name": "변경 용이성", "desc": "새 요구사항에 맞춰 수정하기 쉬운 정도",
        "indicators": ["결합도(Coupling)", "응집도(Cohesion)", "순환 의존성"],
        "remediation_weight": 1.1,
    },
    "efficiency": {
        "name": "효율성", "desc": "자원(CPU, 메모리, I/O)을 적절히 사용하는 정도",
        "indicators": ["시간 복잡도", "메모리 사용량", "DB 쿼리 최적화"],
        "remediation_weight": 0.9,
    },
    "security": {
        "name": "보안성", "desc": "무단 접근/변조에 대한 보호 수준",
        "indicators": ["입력 검증", "인증/인가", "데이터 암호화", "의존성 취약점"],
        "remediation_weight": 1.3,
    },
    "maintainability": {
        "name": "유지보수성", "desc": "코드를 이해하고 수정하기 쉬운 정도",
        "indicators": ["코드 복잡도", "네이밍 품질", "문서화 수준", "모듈 구조"],
        "remediation_weight": 1.0,
    },
    "portability": {
        "name": "이식성", "desc": "다른 환경으로 이전하기 쉬운 정도",
        "indicators": ["환경 의존성 수준", "설정 외부화", "플랫폼 특정 코드"],
        "remediation_weight": 0.7,
    },
    "reusability": {
        "name": "재사용성", "desc": "다른 시스템/모듈에서 재사용할 수 있는 정도",
        "indicators": ["모듈 독립성", "인터페이스 설계", "범용성 수준"],
        "remediation_weight": 0.6,
    },
}

# ─── Martin Fowler's Technical Debt Quadrant (2009) ───────────────

_FOWLER_QUADRANT: dict[str, dict] = {
    "deliberate_prudent": {
        "label": "의도적-신중 (Deliberate-Prudent)", "risk": "중간",
        "desc": "\"일단 출시하고, 나중에 리팩토링하자\" — 시장 선점이 기술 완성도보다 중요할 때",
        "example": "MVP를 위해 모놀리식으로 빠르게 개발 후 마이크로서비스 전환 계획",
        "strategy": "상환 계획 미리 수립, 출시 후 즉시 리팩토링 스프린트 배정",
    },
    "deliberate_reckless": {
        "label": "의도적-무모 (Deliberate-Reckless)", "risk": "높음",
        "desc": "\"설계할 시간 없어, 그냥 복붙하자\" — 일정 압박으로 품질 의도적 무시",
        "example": "같은 로직 5곳 복사-붙여넣기, 하드코딩된 설정값",
        "strategy": "즉시 상환 필요. 기술부채 비용이 기하급수적으로 증가",
    },
    "inadvertent_prudent": {
        "label": "무의식-신중 (Inadvertent-Prudent)", "risk": "낮음",
        "desc": "\"이제야 어떻게 했어야 하는지 알겠다\" — 경험 축적 후 깨닫는 더 나은 방법",
        "example": "프로젝트 완료 후 더 나은 아키텍처 패턴 발견",
        "strategy": "자연스러운 학습 과정. 다음 이터레이션에서 점진적 개선",
    },
    "inadvertent_reckless": {
        "label": "무의식-무모 (Inadvertent-Reckless)", "risk": "치명적",
        "desc": "\"레이어링이 뭐예요?\" — 기술적 역량 부족으로 발생하는 부채",
        "example": "SQL 인젝션 취약점 방치, 전역 변수 남용",
        "strategy": "코드 리뷰 강화 + 팀 교육 + 페어 프로그래밍. 근본 원인 해결",
    },
}

# ─── WSJF 우선순위 기본 가중치 (SAFe Framework) ───────────────────

_WSJF_FACTORS: dict[str, dict] = {
    "business_value": {"name": "사업 가치", "desc": "상환 시 얻는 비즈니스 이점", "scale": "1~13(피보나치)"},
    "time_criticality": {"name": "시간 긴급성", "desc": "지연 시 증가하는 비용/리스크", "scale": "1~13(피보나치)"},
    "risk_reduction": {"name": "리스크 감소", "desc": "상환으로 제거되는 위험/열리는 기회", "scale": "1~13(피보나치)"},
    "job_size": {"name": "작업 규모", "desc": "상환에 필요한 노력/시간", "scale": "1~13(피보나치)"},
}

# ─── 기술부채 측정 지표 벤치마크 ──────────────────────────────

_METRIC_BENCHMARKS: dict[str, dict] = {
    "debt_ratio": {
        "name": "부채 비율 (Debt Ratio)",
        "formula": "기술부채 해결 시간 / 전체 개발 시간",
        "good": "< 5%", "warning": "5% ~ 15%", "critical": "> 15%",
        "source": "SQALE (Letouzey, 2012)",
    },
    "code_coverage": {
        "name": "코드 커버리지 (Code Coverage)",
        "formula": "테스트 실행 코드 / 전체 코드 라인",
        "good": "> 80%", "warning": "60% ~ 80%", "critical": "< 60%",
        "source": "Google Engineering Practices (2024)",
    },
    "cyclomatic_complexity": {
        "name": "순환 복잡도 (Cyclomatic Complexity)",
        "formula": "독립적 실행 경로 수 (McCabe, 1976)",
        "good": "< 10", "warning": "10 ~ 20", "critical": "> 20",
        "source": "McCabe (1976), SEI/CERT",
    },
    "dependency_freshness": {
        "name": "의존성 최신도",
        "formula": "최신 버전 의존성 수 / 전체 의존성 수",
        "good": "> 90%", "warning": "70% ~ 90%", "critical": "< 70%",
        "source": "npm audit, Snyk (2024)",
    },
    "mttr": {
        "name": "평균 복구 시간 (MTTR)",
        "formula": "장애 발생 ~ 복구까지 평균 소요 시간",
        "good": "< 1시간", "warning": "1 ~ 4시간", "critical": "> 4시간",
        "source": "DORA Metrics (Google, 2024)",
    },
    "deploy_frequency": {
        "name": "배포 빈도",
        "formula": "프로덕션 배포 횟수 / 기간",
        "good": "일 1회 이상", "warning": "주 1~3회", "critical": "월 1회 미만",
        "source": "DORA Metrics (Google, 2024)",
    },
    "lead_time": {
        "name": "변경 리드 타임",
        "formula": "코드 커밋 ~ 프로덕션 배포까지 소요 시간",
        "good": "< 1일", "warning": "1일 ~ 1주", "critical": "> 1주",
        "source": "DORA Metrics (Google, 2024)",
    },
    "change_failure_rate": {
        "name": "변경 실패율",
        "formula": "배포 후 장애 발생 횟수 / 전체 배포 횟수",
        "good": "< 5%", "warning": "5% ~ 15%", "critical": "> 15%",
        "source": "DORA Metrics (Google, 2024)",
    },
}


class TechDebtAnalyzerTool(BaseTool):
    """기술부채 분석 도구 — SQALE + Fowler Quadrant + WSJF로 기술부채를 과학적으로 측정하고 상환 전략을 수립합니다."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "full")
        actions = {
            "full": self._full_report,
            "assess": self._assess,
            "classify": self._classify,
            "smells": self._detect_smells,
            "impact": self._impact_analysis,
            "prioritize": self._prioritize,
            "roadmap": self._roadmap,
            "metrics": self._metrics,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return (
            f"알 수 없는 action: {action}. "
            "assess, classify, smells, impact, prioritize, roadmap, metrics, full 중 하나를 사용하세요."
        )

    # ── Full: 전체 종합 리포트 (병렬 실행) ────────────────────────

    async def _full_report(self, p: dict) -> str:
        results = await asyncio.gather(
            self._assess(p),
            self._classify(p),
            self._detect_smells(p),
            self._impact_analysis(p),
            self._prioritize(p),
            self._roadmap(p),
            self._metrics(p),
        )

        sections = [
            ("1. 기술부채 종합 평가 (SQALE)", results[0]),
            ("2. 부채 유형 분류 (Fowler's Quadrant)", results[1]),
            ("3. 코드 스멜 탐지", results[2]),
            ("4. 비즈니스 영향도 분석", results[3]),
            ("5. 상환 우선순위 (WSJF)", results[4]),
            ("6. 상환 로드맵", results[5]),
            ("7. 기술부채 측정 지표", results[6]),
        ]

        lines = ["# 기술부채 종합 분석 리포트", ""]
        for title, content in sections:
            lines.extend([f"## {title}", content, "", "---", ""])

        lines.extend([
            "## 참고 문헌",
            "- Ward Cunningham, *The WyCash Portfolio Management System*, OOPSLA 1992",
            "- Martin Fowler, *Refactoring: Improving the Design of Existing Code*, 2nd ed., 2018",
            "- Martin Fowler, *Technical Debt Quadrant*, martinfowler.com, 2009",
            "- Jean-Louis Letouzey, *The SQALE Method*, 2012",
            "- SAFe (Scaled Agile Framework), *WSJF Prioritization*",
            "- Google DORA Team, *Accelerate: State of DevOps Report*, 2024",
        ])
        return "\n".join(lines)

    # ── Assess: SQALE 기반 종합 평가 ──────────────────────────

    async def _assess(self, p: dict) -> str:
        codebase = p.get("codebase", "")
        project_info = p.get("project_info", "")
        languages = p.get("languages", "Python")
        team_size = int(p.get("team_size", 0))
        codebase_age_months = int(p.get("codebase_age_months", 0))

        context_parts = []
        if codebase:
            context_parts.append(f"코드베이스:\n{codebase}")
        if project_info:
            context_parts.append(f"프로젝트 정보:\n{project_info}")
        if languages:
            context_parts.append(f"주 사용 언어: {languages}")
        if team_size > 0:
            context_parts.append(f"팀 규모: {team_size}명")
        if codebase_age_months > 0:
            context_parts.append(f"코드베이스 나이: {codebase_age_months}개월")

        sqale_desc = "\n".join(
            f"- {v['name']}: {v['desc']} (가중치: {v['remediation_weight']})"
            for v in _SQALE_CHARACTERISTICS.values()
        )

        system_prompt = (
            "당신은 소프트웨어 품질 전문 분석가입니다. SQALE 방법론(Letouzey, 2012)에 따라 "
            "기술부채를 8가지 품질 특성 기준으로 평가합니다.\n\n"
            f"SQALE 8가지 품질 특성:\n{sqale_desc}\n\n"
            "각 특성에 대해 A(우수)~E(심각) 등급을 부여하고 구체적 근거를 제시하세요.\n"
            "전체 기술부채 점수(Technical Debt Ratio)를 백분율로 산출하세요.\n"
            "모든 분석은 한국어 마크다운으로 출력하세요."
        )
        user_prompt = "\n".join(context_parts) if context_parts else (
            "CORTHEX HQ 프로젝트에 대한 일반적인 SQALE 기술부채 평가를 수행하세요. "
            "Python/FastAPI 기반 웹 애플리케이션, AI 에이전트 시스템입니다."
        )
        return await self._llm_call(system_prompt, user_prompt)

    # ── Classify: Fowler Quadrant 기반 부채 유형 분류 ─────────────

    async def _classify(self, p: dict) -> str:
        debt_items = p.get("debt_items", "")
        codebase = p.get("codebase", "")

        quadrant_desc = "\n".join(
            f"- {v['label']}: {v['desc']}\n  예시: {v['example']}\n  위험도: {v['risk']}\n  전략: {v['strategy']}"
            for v in _FOWLER_QUADRANT.values()
        )

        debt_type_desc = "\n".join(
            f"- {v['name']}: {v['desc']} (심각도 가중치: {v['severity_weight']})"
            for v in _DEBT_TYPES.values()
        )

        system_prompt = (
            "당신은 기술부채 분류 전문가입니다.\n\n"
            "Martin Fowler의 Technical Debt Quadrant(2009)를 사용하여 부채를 분류합니다:\n"
            f"{quadrant_desc}\n\n"
            "또한 부채 유형을 다음 6가지로 분류합니다:\n"
            f"{debt_type_desc}\n\n"
            "각 부채 항목에 대해:\n"
            "1. Fowler Quadrant 위치 (의도적/무의식 x 신중/무모)\n"
            "2. 6가지 유형 중 해당 유형\n"
            "3. 위험도 등급 (낮음/중간/높음/치명적)\n"
            "4. 권장 대응 전략\n"
            "을 제시하세요. 한국어 마크다운으로 출력하세요."
        )
        context = debt_items if debt_items else codebase
        user_prompt = context if context else (
            "Python/FastAPI 웹 애플리케이션에서 일반적으로 발생하는 기술부채를 "
            "Fowler Quadrant와 6가지 유형으로 분류하여 예시와 함께 분석하세요."
        )
        return await self._llm_call(system_prompt, user_prompt)

    # ── Smells: Martin Fowler 코드 스멜 탐지 ─────────────────────

    async def _detect_smells(self, p: dict) -> str:
        codebase = p.get("codebase", "")
        file_list = p.get("file_list", "")

        smells_desc = "\n".join(
            f"- {v['name']}: {v['desc']}\n  기준: {v['threshold']} | 리팩토링: {v['refactoring']} | 심각도: {v['severity']}"
            for v in _CODE_SMELLS.values()
        )

        system_prompt = (
            "당신은 Martin Fowler의 'Refactoring'(2018) 전문가입니다.\n"
            "다음 14가지 코드 스멜을 기준으로 코드를 분석합니다:\n\n"
            f"{smells_desc}\n\n"
            "각 발견된 코드 스멜에 대해:\n"
            "1. 스멜 이름과 위치\n"
            "2. 구체적 증거 (코드 스니펫 또는 패턴)\n"
            "3. 심각도 (낮음/중간/높음/치명적)\n"
            "4. 권장 리팩토링 기법\n"
            "5. 예상 개선 효과\n"
            "를 표 형태로 정리하세요. 한국어 마크다운으로 출력하세요."
        )
        user_prompt = codebase if codebase else (
            file_list if file_list else
            "Python/FastAPI 프로젝트에서 흔히 발견되는 코드 스멜을 "
            "14가지 카탈로그 기준으로 분석하고 리팩토링 방안을 제시하세요."
        )
        return await self._llm_call(system_prompt, user_prompt)

    # ── Impact: 비즈니스 영향도 분석 ──────────────────────────

    async def _impact_analysis(self, p: dict) -> str:
        system_prompt = (
            "당신은 기술부채의 비즈니스 영향을 분석하는 전문가입니다.\n\n"
            "3가지 축으로 분석합니다:\n"
            "1. **개발 속도**: 부채 1% 증가 → 속도 2~4% 감소 (Stripe 2018)\n"
            "2. **시스템 안정성**: 부채 방치 시 연간 장애율 30~50% 증가 (DORA)\n"
            "3. **인재 채용/유지**: 레거시 코드베이스 이직 확률 2.5배 (Stack Overflow)\n\n"
            "정량적 추정치 + '기술부채 이자(Interest)' 월/분기별 비용 산출.\n"
            "한국어 마크다운으로 출력하세요."
        )
        context_parts = []
        for key, label in [("debt_items", "기술부채 항목"), ("project_info", "프로젝트 정보")]:
            if p.get(key):
                context_parts.append(f"{label}:\n{p[key]}")
        if int(p.get("team_size", 0)) > 0:
            context_parts.append(f"팀 규모: {p['team_size']}명")
        if p.get("monthly_revenue"):
            context_parts.append(f"월 매출: {p['monthly_revenue']}")

        user_prompt = "\n".join(context_parts) if context_parts else (
            "스타트업 규모(5~10명)의 Python 웹 서비스에서 기술부채가 "
            "개발 속도, 시스템 안정성, 인재 채용/유지에 미치는 영향을 분석하세요."
        )
        return await self._llm_call(system_prompt, user_prompt)

    # ── Prioritize: WSJF 기반 상환 우선순위 ────────────────────

    async def _prioritize(self, p: dict) -> str:
        wsjf_desc = "\n".join(f"- {v['name']}: {v['desc']} ({v['scale']})" for v in _WSJF_FACTORS.values())

        system_prompt = (
            "SAFe WSJF 전문가로서 기술부채 상환 우선순위를 결정합니다.\n"
            "**WSJF = Cost of Delay / Job Duration**\n"
            "**Cost of Delay = Business Value + Time Criticality + Risk Reduction**\n\n"
            f"평가 요소:\n{wsjf_desc}\n\n"
            "각 항목: 피보나치 점수(1~13), CoD 합산, WSJF 점수, 우선순위를 표로.\n"
            "한국어 마크다운으로 출력하세요."
        )
        user_prompt = p.get("debt_items") or (
            "다음 기술부채 항목의 WSJF 우선순위를 매겨주세요:\n"
            "1. 테스트 커버리지 부족 (30%) 2. 모놀리식 아키텍처 분리\n"
            "3. 오래된 의존성 업데이트 4. API 문서 자동화\n"
            "5. CI/CD 파이프라인 개선 6. 에러 핸들링 표준화\n"
            "7. DB 스키마 정규화 8. 로깅/모니터링 체계 구축"
        )
        if p.get("sprint_capacity"):
            user_prompt += f"\n\n스프린트 용량: {p['sprint_capacity']}"
        return await self._llm_call(system_prompt, user_prompt)

    # ── Roadmap: Sprint 단위 상환 로드맵 ──────────────────────

    async def _roadmap(self, p: dict) -> str:
        sprints = int(p.get("sprints", 6))
        sprint_days = int(p.get("sprint_days", 10))
        debt_budget_pct = float(p.get("debt_budget_pct", 0.20))

        system_prompt = (
            "당신은 기술부채 상환 로드맵 전문가입니다.\n\n"
            "원칙: 1) 20% 규칙(Fowler) 2) 의존성 순서 3) Quick Win 우선 "
            "4) Strangler Fig 패턴 5) 정량적 목표 설정\n\n"
            f"계획: {sprints} 스프린트 ({sprint_days}일/스프린트), 부채 예산 {debt_budget_pct:.0%}\n\n"
            "각 스프린트: 상환 대상, 스토리포인트, DoD, 개선 효과, 리스크.\n"
            "한국어 마크다운으로 출력하세요."
        )
        context_parts = []
        if p.get("debt_items"):
            context_parts.append(f"상환 대상:\n{p['debt_items']}")
        if int(p.get("team_size", 0)) > 0:
            context_parts.append(f"팀 규모: {p['team_size']}명")

        user_prompt = "\n".join(context_parts) if context_parts else (
            f"Python/FastAPI 웹 애플리케이션의 일반적 기술부채에 대한 "
            f"{sprints} 스프린트 상환 로드맵을 작성하세요."
        )
        return await self._llm_call(system_prompt, user_prompt)

    # ── Metrics: 기술부채 측정 지표 대시보드 ─────────────────────

    async def _metrics(self, p: dict) -> str:
        current_metrics = p.get("current_metrics", {})
        project_info = p.get("project_info", "")

        benchmark_lines = [
            "### 기술부채 측정 지표 벤치마크", "",
            "| 지표 | 산출 공식 | 양호 | 주의 | 위험 | 출처 |",
            "|------|---------|------|------|------|------|",
        ]
        for m in _METRIC_BENCHMARKS.values():
            benchmark_lines.append(
                f"| {m['name']} | {m['formula']} | {m['good']} | {m['warning']} | {m['critical']} | {m['source']} |"
            )
        benchmark_table = "\n".join(benchmark_lines)

        if current_metrics or project_info:
            system_prompt = (
                "소프트웨어 품질 메트릭 전문가로서 벤치마크 기준으로 평가하세요:\n\n"
                f"{benchmark_table}\n\n"
                "각 지표: 등급(양호/주의/위험), 우선순위, 개선 방안, 목표치. 한국어 마크다운."
            )
            parts = []
            if current_metrics:
                parts.append("현재 측정값:\n" + "\n".join(f"- {k}: {v}" for k, v in current_metrics.items()))
            if project_info:
                parts.append(f"프로젝트 정보:\n{project_info}")
            return f"{benchmark_table}\n\n---\n\n{await self._llm_call(system_prompt, chr(10).join(parts))}"

        system_prompt = (
            "소프트웨어 품질 메트릭 전문가입니다.\n\n" + benchmark_table + "\n\n"
            "8가지 지표 측정 가이드: 도구/명령어, 자동화, 개선 전략. DORA 4대 지표 강조.\n"
            "한국어 마크다운으로 출력하세요."
        )
        user_prompt = "Python/FastAPI 프로젝트에서 기술부채 측정 지표를 수집하고 대시보드화하는 방법을 안내하세요."
        return f"{benchmark_table}\n\n---\n\n{await self._llm_call(system_prompt, user_prompt)}"
