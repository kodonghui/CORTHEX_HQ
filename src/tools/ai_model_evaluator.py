"""
AI 모델 평가 도구 (AI Model Evaluator) — 대규모 언어모델을 과학적으로 평가하고 비교합니다.

HELM(Holistic Evaluation of Language Models) 프레임워크 기반의 6차원 평가,
Chatbot Arena ELO 시스템, 표준 벤치마크(MMLU, HumanEval, MT-Bench, GSM8K, BBH)를
종합하여 모델별 강약점을 정량적으로 분석합니다.

학술 근거:
  - Liang et al., "Holistic Evaluation of Language Models" (Stanford CRFM, 2023)
  - Zheng et al., "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena" (LMSYS, NeurIPS 2024)
  - OpenAI, "GPT-4 Technical Report" (arXiv:2303.08774, 2023)
  - Bai et al., "Constitutional AI: Harmlessness from AI Feedback" (Anthropic, arXiv:2212.08073, 2022)

사용 방법:
  - action="evaluate"  : AI 모델 종합 평가 (HELM 프레임워크)
  - action="compare"   : 모델 간 비교 분석 (GPT vs Claude vs Gemini vs Open-Source)
  - action="select"    : 용도별 모델 추천 (비용/성능/지연시간 트레이드오프)
  - action="benchmark" : 벤치마크 분석 (MMLU, HumanEval, MT-Bench, Arena ELO)
  - action="cost"      : 비용 최적화 분석 (토큰 단가, 배치 할인, 캐싱 전략)
  - action="safety"    : AI 안전성 평가 (Hallucination, Bias, Toxicity, Privacy)
  - action="deploy"    : 배포 전략 자문 (Fine-tuning vs RAG vs Prompt Engineering)
  - action="prompt"    : 프롬프트 엔지니어링 분석 (CoT, Few-shot, ReAct)
  - action="full"      : 전체 종합 리포트 (asyncio.gather 병렬 실행)

필요 환경변수: 없음 (LLM 호출은 BaseTool._llm_call 사용)
필요 라이브러리: 없음 (표준 라이브러리 + asyncio)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.ai_model_evaluator")

# ─── 모델 패밀리 정보 (2024~2025 기준) ────────────────────────────

_MODEL_FAMILIES: dict[str, dict] = {
    "GPT": {
        "provider": "OpenAI",
        "models": ["GPT-5.2 Pro", "GPT-5.2", "GPT-5", "GPT-5 Mini"],
        "strengths": ["광범위한 범용 능력", "Function Calling 안정성", "대규모 생태계"],
        "weaknesses": ["비용 상대적 고가", "할루시네이션 관리 필요", "폐쇄형 모델"],
    },
    "Claude": {
        "provider": "Anthropic",
        "models": ["Claude Opus 4.6", "Claude Sonnet 4.6", "Claude Haiku 4.5"],
        "strengths": ["긴 컨텍스트 윈도우", "Constitutional AI 안전성", "코드 생성 우수"],
        "weaknesses": ["멀티모달 기능 후발", "리전 제한", "배치 처리 옵션 제한"],
    },
    "Gemini": {
        "provider": "Google DeepMind",
        "models": ["Gemini 3.0 Pro", "Gemini 2.5 Pro", "Gemini 2.5 Flash"],
        "strengths": ["네이티브 멀티모달", "긴 컨텍스트(1M+)", "Google 생태계 통합"],
        "weaknesses": ["API 안정성 변동", "프롬프트 호환성 차이", "엔터프라이즈 지원 미성숙"],
    },
    "Open-Source": {
        "provider": "Meta / Mistral / etc.",
        "models": ["Llama 3.1 405B", "Mixtral 8x22B", "Qwen-2.5 72B", "DeepSeek-V3"],
        "strengths": ["자체 호스팅 가능", "커스터마이징 자유", "데이터 프라이버시"],
        "weaknesses": ["인프라 운영 부담", "상위 모델 대비 성능 갭", "Fine-tuning 전문성 필요"],
    },
}

# ─── 주요 벤치마크 정의 ──────────────────────────────────────────

_BENCHMARKS: dict[str, dict] = {
    "MMLU": {
        "full_name": "Massive Multitask Language Understanding",
        "description": "57개 학문 분야 4지선다 (초등~전문가 수준)",
        "metric": "정확도 (%)", "reference": "Hendrycks et al. (2021)", "top_score": "90.0%+",
    },
    "HumanEval": {
        "full_name": "OpenAI HumanEval Code Generation",
        "description": "164개 Python 함수 생성 + 유닛테스트 통과율",
        "metric": "pass@1 (%)", "reference": "Chen et al. (2021)", "top_score": "92.0%+",
    },
    "MT-Bench": {
        "full_name": "Multi-Turn Benchmark",
        "description": "8개 카테고리 다중 턴 대화 품질 (GPT-4 심사)",
        "metric": "점수 (1~10)", "reference": "Zheng et al. (2024, LMSYS)", "top_score": "9.5+",
    },
    "Arena_ELO": {
        "full_name": "Chatbot Arena ELO Rating",
        "description": "블라인드 A/B 인간 선호도 투표 기반 ELO 레이팅",
        "metric": "ELO 점수", "reference": "LMSYS Chatbot Arena (2024)", "top_score": "1350+",
    },
    "GSM8K": {
        "full_name": "Grade School Math 8K",
        "description": "초등~중등 수준 수학 문제 8,500개",
        "metric": "정확도 (%)", "reference": "Cobbe et al. (2021)", "top_score": "97.0%+",
    },
    "BBH": {
        "full_name": "BIG-Bench Hard",
        "description": "23개 난제 태스크 (기존 LM이 인간 이하 성능)",
        "metric": "정확도 (%)", "reference": "Suzgun et al. (2023)", "top_score": "88.0%+",
    },
}

# ─── HELM 6차원 평가 프레임워크 (Stanford CRFM, 2023) ──────────

_EVALUATION_DIMS: dict[str, dict] = {
    "accuracy":    {"name_ko": "정확성 (Accuracy)",    "sub_metrics": ["사실 정확도", "논리적 일관성", "수학/추론 정확도"], "weight": 0.25},
    "robustness":  {"name_ko": "견고성 (Robustness)",  "sub_metrics": ["프롬프트 변형 내성", "적대적 공격 방어", "일관된 출력 품질"], "weight": 0.15},
    "calibration": {"name_ko": "보정성 (Calibration)", "sub_metrics": ["불확실성 표현", "자기 인식", "거절 적절성"], "weight": 0.15},
    "fairness":    {"name_ko": "공정성 (Fairness)",    "sub_metrics": ["성별 편향", "인종/문화 편향", "지역/언어 편향"], "weight": 0.15},
    "efficiency":  {"name_ko": "효율성 (Efficiency)",  "sub_metrics": ["추론 지연시간", "토큰당 비용", "처리량(TPS)"], "weight": 0.15},
    "safety":      {"name_ko": "안전성 (Safety)",      "sub_metrics": ["유해 콘텐츠 필터링", "개인정보 보호", "편향 완화"], "weight": 0.15},
}

# ─── 배포 전략 비교 ──────────────────────────────────────────────

_DEPLOYMENT_STRATEGIES: dict[str, dict] = {
    "fine_tuning": {
        "name_ko": "Fine-tuning (미세 조정)",
        "description": "도메인 특화 데이터로 모델 가중치를 직접 조정",
        "pros": ["도메인 특화 성능 극대화", "추론 시 추가 컨텍스트 불필요", "일관된 출력 스타일"],
        "cons": ["학습 데이터 수천~수만 건 필요", "학습 비용 + GPU 시간", "모델 업데이트 시 재학습"],
        "best_for": ["반복적 도메인 태스크", "고정된 출력 포맷", "대량 처리"],
        "cost_range": "중~고", "time_to_deploy": "2~6주", "data_requirement": "1,000~50,000+ 예시",
    },
    "rag": {
        "name_ko": "RAG (검색 증강 생성)",
        "description": "외부 지식 베이스를 검색하여 컨텍스트에 주입 후 생성",
        "pros": ["지식 실시간 업데이트", "할루시네이션 감소", "데이터 소스 추적 가능"],
        "cons": ["검색 품질에 의존", "긴 컨텍스트 비용 증가", "임베딩 인프라 필요"],
        "best_for": ["자주 변경되는 지식", "근거 기반 답변", "다양한 도메인"],
        "cost_range": "중", "time_to_deploy": "1~3주", "data_requirement": "문서 코퍼스 (크기 무관)",
    },
    "prompt_engineering": {
        "name_ko": "Prompt Engineering (프롬프트 공학)",
        "description": "시스템 프롬프트, Few-shot 예시, CoT 등으로 행동 제어",
        "pros": ["즉시 적용 가능", "비용 최소", "A/B 테스트 용이"],
        "cons": ["복잡한 도메인 한계", "컨텍스트 길이 제약", "프롬프트 인젝션 위험"],
        "best_for": ["빠른 프로토타이핑", "범용 태스크", "저예산 프로젝트"],
        "cost_range": "저", "time_to_deploy": "수 시간~수 일", "data_requirement": "예시 5~20개",
    },
}

# ─── 모델별 비용 등급 (2025년 기준 근사치, USD/1M tokens) ────────

_COST_TIERS: dict[str, dict] = {
    "premium":     {"name_ko": "프리미엄",   "input_per_1m": 15.0,  "output_per_1m": 75.0,  "models": ["Claude Opus 4.6", "GPT-5.2 Pro"]},
    "standard":    {"name_ko": "스탠다드",   "input_per_1m": 3.0,   "output_per_1m": 15.0,  "models": ["Claude Sonnet 4.6", "GPT-5.2", "GPT-5", "Gemini 3.0 Pro"]},
    "economy":     {"name_ko": "이코노미",   "input_per_1m": 0.25,  "output_per_1m": 1.25,  "models": ["Claude Haiku 4.5", "GPT-5 Mini", "Gemini 2.5 Flash"]},
    "self_hosted": {"name_ko": "자체 호스팅", "input_per_1m": 0.0,   "output_per_1m": 0.0,   "models": ["Llama 3.1 405B", "Mixtral 8x22B", "Qwen-2.5 72B"]},
}

# ─── 프롬프트 엔지니어링 기법 ────────────────────────────────────

_PROMPTING_TECHNIQUES: dict[str, dict] = {
    "zero_shot":        {"name_ko": "Zero-shot",               "description": "예시 없이 지시문만으로 수행",                          "effectiveness": "기본",              "use_case": "단순 분류, 번역, 요약"},
    "few_shot":         {"name_ko": "Few-shot",                "description": "2~5개 입출력 예시를 프롬프트에 포함",                   "effectiveness": "높음",              "use_case": "포맷 일관성, 도메인 적응"},
    "cot":              {"name_ko": "Chain-of-Thought (CoT)",  "description": "단계별 사고 과정을 유도하여 추론 정확도 향상",          "effectiveness": "매우 높음 (추론)",    "use_case": "수학, 논리, 복잡한 분석"},
    "react":            {"name_ko": "ReAct",                   "description": "사고-행동-관찰 루프로 도구 사용과 추론을 결합",         "effectiveness": "매우 높음 (에이전트)", "use_case": "도구 호출, 정보 검색"},
    "self_consistency": {"name_ko": "Self-Consistency",        "description": "동일 질문을 여러 번 샘플링하여 다수결로 최종 답 선택",  "effectiveness": "높음 (정답 태스크)",  "use_case": "수학, 객관식, 사실 확인"},
    "tree_of_thought":  {"name_ko": "Tree-of-Thought (ToT)",  "description": "여러 사고 경로를 트리 형태로 탐색 후 최적 경로 선택",   "effectiveness": "최고 (복잡 추론)",    "use_case": "전략 계획, 복잡한 문제"},
}


class AIModelEvaluatorTool(BaseTool):
    """AI 모델 평가 도구 — HELM 프레임워크 기반 종합 평가, 비교, 추천, 비용 분석."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "evaluate")
        actions = {
            "evaluate": self._evaluate_model, "compare": self._compare_models,
            "select": self._select_model, "benchmark": self._benchmark_analysis,
            "cost": self._cost_optimization, "safety": self._safety_evaluation,
            "deploy": self._deploy_strategy, "prompt": self._prompt_engineering,
            "full": self._full_report,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return f"알 수 없는 action: {action}. 사용 가능: {', '.join(actions.keys())}"

    # ── 1. evaluate: HELM 기반 종합 평가 ─────────────────────

    async def _evaluate_model(self, p: dict) -> str:
        model_name = p.get("model", "")
        use_case = p.get("use_case", "범용")
        context = p.get("context", "")

        if not model_name:
            lines = ["### AI 모델 평가 — 입력 필요:", "",
                      "| 파라미터 | 설명 | 예시 |", "|---------|------|------|",
                      "| model | 평가 모델명 | GPT-5.2, Claude Sonnet 4.6 |",
                      "| use_case | 용도 | 코드 생성, 고객 상담 |",
                      "| context | 추가 맥락 (선택) | 한국어 위주 |", "",
                      "### HELM 6차원:", "| 차원 | 가중치 | 세부 지표 |", "|------|--------|----------|"]
            for d in _EVALUATION_DIMS.values():
                lines.append(f"| {d['name_ko']} | {d['weight']:.0%} | {', '.join(d['sub_metrics'])} |")
            return "\n".join(lines)

        system_prompt = (
            "당신은 Stanford HELM 프레임워크(Liang et al., 2023)에 기반한 AI 모델 평가 전문가입니다.\n"
            "6가지 평가 차원(정확성, 견고성, 보정성, 공정성, 효율성, 안전성)으로 모델을 분석합니다.\n"
            "반드시 한국어 마크다운으로, 각 차원 10점 만점 점수와 근거, 총평과 추천을 포함하세요."
        )
        user_prompt = f"## 평가 대상: {model_name}\n## 용도: {use_case}\n## 맥락: {context or '없음'}\n\nHELM 6차원 평가:\n"
        for dim in _EVALUATION_DIMS.values():
            user_prompt += f"- {dim['name_ko']} ({dim['weight']:.0%}): {', '.join(dim['sub_metrics'])}\n"
        user_prompt += "\n각 차원별 점수(10점), 분석, 종합 점수, 강점/약점, 용도 적합도를 표로 정리하세요."

        analysis = await self._llm_call(system_prompt, user_prompt)
        return "\n".join([
            f"# AI 모델 종합 평가: {model_name}", "",
            f"**프레임워크**: Stanford HELM (Liang et al., 2023) | **용도**: {use_case}", "",
            analysis, "", "---",
            "**참고**: Liang et al., 'Holistic Evaluation of Language Models' (Stanford CRFM, 2023)",
        ])

    # ── 2. compare: 모델 간 비교 분석 ────────────────────────

    async def _compare_models(self, p: dict) -> str:
        models = p.get("models", "")
        criteria = p.get("criteria", "성능, 비용, 지연시간, 안전성")
        use_case = p.get("use_case", "범용")

        if not models:
            lines = ["### 모델 비교 — 입력 필요:", "",
                      "| 파라미터 | 설명 | 예시 |", "|---------|------|------|",
                      "| models | 비교 모델 (쉼표 구분) | GPT-5.2, Claude Sonnet 4.6 |",
                      "| criteria | 비교 기준 (선택) | 성능, 비용, 지연시간 |", "",
                      "### 모델 패밀리:", "| 패밀리 | 제공사 | 대표 모델 |", "|--------|--------|----------|"]
            for f, i in _MODEL_FAMILIES.items():
                lines.append(f"| {f} | {i['provider']} | {', '.join(i['models'][:3])} |")
            return "\n".join(lines)

        system_prompt = (
            "당신은 AI 모델 비교 분석가입니다. Chatbot Arena ELO(LMSYS, 2024), MMLU, HumanEval 등 "
            "공인 벤치마크 기반으로 모델 간 차이를 객관적으로 분석합니다.\n"
            "한국어 마크다운 비교표 + 각 기준별 승자 + 종합 추천을 제시하세요."
        )
        user_prompt = f"## 비교 대상: {models}\n## 기준: {criteria}\n## 용도: {use_case}\n\n모델 패밀리:\n"
        for fam, info in _MODEL_FAMILIES.items():
            user_prompt += f"- {fam} ({info['provider']}): 강점={', '.join(info['strengths'][:2])}\n"
        user_prompt += "\n비교 기준별 상세 분석, 비교표, 기준별 승자, 종합 추천을 제시하세요."

        analysis = await self._llm_call(system_prompt, user_prompt)
        return "\n".join([
            "# AI 모델 비교 분석", "",
            f"**대상**: {models} | **기준**: {criteria} | **용도**: {use_case}", "",
            analysis, "", "---", "**참고**: LMSYS Chatbot Arena (2024), Stanford HELM (2023)",
        ])

    # ── 3. select: 용도별 모델 추천 ──────────────────────────

    async def _select_model(self, p: dict) -> str:
        use_case = p.get("use_case", "")
        budget = p.get("budget", "")
        volume = p.get("volume", "")
        latency_req = p.get("latency", "")

        if not use_case:
            lines = ["### 모델 추천 — 입력 필요:", "",
                      "| 파라미터 | 설명 | 예시 |", "|---------|------|------|",
                      "| use_case | 용도 | 고객 상담, 코드 리뷰 |",
                      "| budget | 월 예산 (선택) | $500/월 |",
                      "| volume | 처리량 (선택) | 일 1만 건 |", "",
                      "### 비용 등급 (USD/1M 토큰):", "| 등급 | 입력 | 출력 | 대표 모델 |", "|------|------|------|----------|"]
            for t in _COST_TIERS.values():
                lines.append(f"| {t['name_ko']} | ${t['input_per_1m']:.2f} | ${t['output_per_1m']:.2f} | {', '.join(t['models'][:2])} |")
            return "\n".join(lines)

        system_prompt = (
            "당신은 AI 모델 선택 컨설턴트입니다. 용도, 예산, 처리량, 지연시간을 분석하여 "
            "1~3순위 모델을 추천합니다. 비용/성능/지연시간 트레이드오프를 정량 분석하세요."
        )
        user_prompt = f"## 용도: {use_case}\n## 예산: {budget or '제한 없음'}\n## 처리량: {volume or '보통'}\n## 지연시간: {latency_req or '무관'}\n\n비용 등급:\n"
        for tier in _COST_TIERS.values():
            user_prompt += f"- {tier['name_ko']}: 입력 ${tier['input_per_1m']}/1M, 출력 ${tier['output_per_1m']}/1M — {', '.join(tier['models'])}\n"
        user_prompt += "\n1~3순위 추천 + 장단점/예상 비용/적합도 표로 정리하세요."

        analysis = await self._llm_call(system_prompt, user_prompt)
        return "\n".join([
            "# 용도별 AI 모델 추천", "",
            f"**용도**: {use_case} | **예산**: {budget or '제한 없음'}", "", analysis,
        ])

    # ── 4. benchmark: 벤치마크 분석 ──────────────────────────

    async def _benchmark_analysis(self, p: dict) -> str:
        model_name = p.get("model", "")
        benchmarks = p.get("benchmarks", "MMLU, HumanEval, MT-Bench, Arena_ELO")

        if not model_name:
            lines = ["### 벤치마크 분석 — 입력 필요:", "",
                      "| 파라미터 | 설명 | 예시 |", "|---------|------|------|",
                      "| model | 모델명 | GPT-5.2, Claude Opus 4.6 |",
                      "| benchmarks | 벤치마크 (선택) | MMLU, HumanEval |", "",
                      "### 지원 벤치마크:", "| 이름 | 설명 | 메트릭 |", "|------|------|--------|"]
            for k, b in _BENCHMARKS.items():
                lines.append(f"| {k} | {b['description'][:35]} | {b['metric']} |")
            return "\n".join(lines)

        system_prompt = (
            "당신은 AI 벤치마크 분석 전문가입니다. MMLU, HumanEval, MT-Bench, Arena ELO, GSM8K, BBH 등 "
            "공인 벤치마크 결과를 분석합니다. 한국어 마크다운으로 점수표, 강약점, 실무 시사점을 작성하세요."
        )
        user_prompt = f"## 대상 모델: {model_name}\n## 벤치마크: {benchmarks}\n\n벤치마크 정보:\n"
        for k, bm in _BENCHMARKS.items():
            user_prompt += f"- {k} ({bm['full_name']}): {bm['description']}, 최고점={bm['top_score']}\n"
        user_prompt += "\n각 벤치마크 예상 성능 + 점수 해석 + 실무 시사점 + 한계를 작성하세요."

        analysis = await self._llm_call(system_prompt, user_prompt)
        return "\n".join([
            f"# 벤치마크 분석: {model_name}", "", analysis, "", "---",
            "**출처**: Hendrycks et al. (2021), Chen et al. (2021), Zheng et al. (2024)",
        ])

    # ── 5. cost: 비용 최적화 분석 ────────────────────────────

    async def _cost_optimization(self, p: dict) -> str:
        model_name = p.get("model", "")
        monthly_tokens = float(p.get("monthly_tokens", 0))
        input_ratio = float(p.get("input_ratio", 0.7))

        if not model_name and monthly_tokens <= 0:
            lines = ["### 비용 분석 — 입력 필요:", "",
                      "| 파라미터 | 설명 | 예시 |", "|---------|------|------|",
                      "| model | 모델명 (선택) | Claude Sonnet 4.6 |",
                      "| monthly_tokens | 월간 토큰 | 10000000 |",
                      "| input_ratio | 입력 비율 (기본 0.7) | 0.7 |", "",
                      "### 비용 등급:", "| 등급 | 입력 | 출력 | 모델 |", "|------|------|------|------|"]
            for t in _COST_TIERS.values():
                lines.append(f"| {t['name_ko']} | ${t['input_per_1m']:.2f} | ${t['output_per_1m']:.2f} | {', '.join(t['models'][:2])} |")
            return "\n".join(lines)

        # 정적 비용 테이블
        cost_lines = self._calculate_cost_table(monthly_tokens, input_ratio)

        system_prompt = (
            "당신은 AI 비용 최적화 컨설턴트입니다. 토큰 단가, 배치 할인, 프롬프트 캐싱, "
            "모델 라우팅 등 비용 절감 전략을 분석합니다. 구체적 절감 금액과 실행 방안을 제시하세요."
        )
        user_prompt = (
            f"## 모델: {model_name or '미정'}\n## 월간 토큰: {monthly_tokens:,.0f}\n"
            f"## 입출력 비율: {input_ratio:.0%}/{1-input_ratio:.0%}\n\n"
            "분석: 1) 현재 비용 구조 2) 절감 전략 3가지 3) 대안 모델 비교 4) ROI 추천"
        )

        analysis = await self._llm_call(system_prompt, user_prompt)
        return "\n".join([
            "# AI 비용 최적화 분석", "",
            f"**월간 토큰**: {monthly_tokens:,.0f} | **입력 비율**: {input_ratio:.0%}", "",
            "## 모델별 월간 비용", "", *cost_lines, "",
            "## 최적화 전략", "", analysis,
        ])

    def _calculate_cost_table(self, monthly_tokens: float, input_ratio: float) -> list[str]:
        if monthly_tokens <= 0:
            return ["(월간 토큰 수를 입력하면 비용을 계산합니다)"]
        inp = monthly_tokens * input_ratio / 1_000_000
        out = monthly_tokens * (1 - input_ratio) / 1_000_000
        lines = ["| 등급 | 대표 모델 | 월 입력 | 월 출력 | **합계** |",
                  "|------|----------|--------|--------|---------|"]
        for t in _COST_TIERS.values():
            ic, oc = inp * t["input_per_1m"], out * t["output_per_1m"]
            total = ic + oc
            m = t["models"][0] if t["models"] else "-"
            if total > 0:
                lines.append(f"| {t['name_ko']} | {m} | ${ic:,.2f} | ${oc:,.2f} | **${total:,.2f}** |")
            else:
                lines.append(f"| {t['name_ko']} | {m} | GPU | GPU | **인프라 별도** |")
        return lines

    # ── 6. safety: AI 안전성 평가 ────────────────────────────

    async def _safety_evaluation(self, p: dict) -> str:
        model_name = p.get("model", "")
        focus = p.get("focus", "hallucination, bias, toxicity, privacy")

        if not model_name:
            return "\n".join([
                "### 안전성 평가 — 입력 필요:", "",
                "| 파라미터 | 설명 | 예시 |", "|---------|------|------|",
                "| model | 모델명 | GPT-5.2, Claude Opus 4.6 |",
                "| focus | 집중 영역 (선택) | hallucination, bias, toxicity, privacy |", "",
                "### 안전성 4축:", "| 축 | 설명 | 주요 위험 |", "|---|------|---------|",
                "| Hallucination | 사실과 다른 정보 생성 | 잘못된 의사결정 |",
                "| Bias | 인구통계적 편향 | 차별적 결과 |",
                "| Toxicity | 유해 콘텐츠 | 법적 리스크 |",
                "| Privacy | 개인정보 유출 | GDPR 위반 |",
            ])

        system_prompt = (
            "당신은 AI 안전성 전문가입니다. Constitutional AI(Bai et al., 2022), RLHF 등 "
            "안전 메커니즘을 이해합니다. 할루시네이션/편향/유해성/프라이버시 4축으로 평가하세요.\n"
            "각 축별 위험 등급(높음/중간/낮음), 사례, 완화 전략을 표로 정리하세요."
        )
        user_prompt = (
            f"## 대상: {model_name}\n## 집중 영역: {focus}\n\n"
            "4축 분석: 1) Hallucination 2) Bias 3) Toxicity 4) Privacy\n"
            "각 축별 위험 등급, 사례, 프로바이더 대응, 사용자 완화 전략을 작성하세요."
        )

        analysis = await self._llm_call(system_prompt, user_prompt)
        return "\n".join([
            f"# AI 안전성 평가: {model_name}", "",
            f"**프레임워크**: Constitutional AI (Anthropic, 2022) + HELM Safety", "",
            analysis, "", "---",
            "**참고**: Bai et al., 'Constitutional AI' (2022); Liang et al., 'HELM' (2023)",
        ])

    # ── 7. deploy: 배포 전략 자문 ────────────────────────────

    async def _deploy_strategy(self, p: dict) -> str:
        use_case = p.get("use_case", "")
        data_size = p.get("data_size", "")
        budget = p.get("budget", "")

        if not use_case:
            lines = ["### 배포 전략 — 입력 필요:", "",
                      "| 파라미터 | 설명 | 예시 |", "|---------|------|------|",
                      "| use_case | 용도 | 고객 상담, 법률 문서 분석 |",
                      "| data_size | 데이터 규모 (선택) | 5,000건 |",
                      "| budget | 예산 (선택) | $2,000/월 |", "",
                      "### 3가지 전략:", "| 전략 | 소요시간 | 데이터 |", "|------|---------|--------|"]
            for s in _DEPLOYMENT_STRATEGIES.values():
                lines.append(f"| {s['name_ko']} | {s['time_to_deploy']} | {s['data_requirement']} |")
            return "\n".join(lines)

        system_prompt = (
            "당신은 AI 배포 전략 아키텍트입니다. Fine-tuning, RAG, Prompt Engineering의 "
            "트레이드오프를 분석하여 최적 전략을 추천합니다. 결정 매트릭스, 로드맵을 포함하세요."
        )
        user_prompt = f"## 용도: {use_case}\n## 데이터: {data_size or '미정'}\n## 예산: {budget or '미정'}\n\n전략:\n"
        for s in _DEPLOYMENT_STRATEGIES.values():
            user_prompt += f"- {s['name_ko']}: {s['description']} (비용: {s['cost_range']}, 시간: {s['time_to_deploy']})\n"
        user_prompt += "\n1) 추천 전략 + 근거 2) 대안/하이브리드 3) 4주 로드맵 4) 예상 비용"

        analysis = await self._llm_call(system_prompt, user_prompt)
        lines = ["# AI 배포 전략 자문", "", f"**용도**: {use_case}", "",
                  "## 전략 비교", "", "| 전략 | 시간 | 비용 | 데이터 |", "|------|------|------|--------|"]
        for s in _DEPLOYMENT_STRATEGIES.values():
            lines.append(f"| {s['name_ko']} | {s['time_to_deploy']} | {s['cost_range']} | {s['data_requirement']} |")
        lines.extend(["", "## 상세 분석", "", analysis])
        return "\n".join(lines)

    # ── 8. prompt: 프롬프트 엔지니어링 분석 ──────────────────

    async def _prompt_engineering(self, p: dict) -> str:
        task_type = p.get("task_type", "")
        current_prompt = p.get("current_prompt", "")
        target_model = p.get("model", "")

        if not task_type:
            lines = ["### 프롬프트 분석 — 입력 필요:", "",
                      "| 파라미터 | 설명 | 예시 |", "|---------|------|------|",
                      "| task_type | 태스크 유형 | 코드 생성, 문서 요약, 분류 |",
                      "| current_prompt | 현재 프롬프트 (선택) | '요약하세요...' |",
                      "| model | 대상 모델 (선택) | Claude Sonnet 4.6 |", "",
                      "### 프롬프트 기법:", "| 기법 | 효과 | 용도 |", "|------|------|------|"]
            for t in _PROMPTING_TECHNIQUES.values():
                lines.append(f"| {t['name_ko']} | {t['effectiveness']} | {t['use_case']} |")
            return "\n".join(lines)

        system_prompt = (
            "당신은 프롬프트 엔지니어링 전문가입니다. CoT(Wei et al., 2022), Few-shot(Brown et al., 2020), "
            "ReAct(Yao et al., 2023), ToT(Yao et al., 2024)를 깊이 이해합니다.\n"
            "한국어 마크다운으로 최적 기법 추천 + 구체적 프롬프트 템플릿을 제시하세요."
        )
        user_prompt = f"## 태스크: {task_type}\n## 모델: {target_model or '미정'}\n## 현재 프롬프트: {current_prompt or '없음'}\n\n기법:\n"
        for t in _PROMPTING_TECHNIQUES.values():
            user_prompt += f"- {t['name_ko']}: {t['description']} (효과: {t['effectiveness']})\n"
        user_prompt += "\n1) 추천 기법 + 근거 2) 프롬프트 템플릿 3) 팁 3가지 4) 기법 조합 전략"

        analysis = await self._llm_call(system_prompt, user_prompt)
        lines = ["# 프롬프트 엔지니어링 분석", "",
                  f"**태스크**: {task_type} | **모델**: {target_model or '범용'}", "",
                  "## 기법 비교", "", "| 기법 | 효과 | 용도 |", "|------|------|------|"]
        for t in _PROMPTING_TECHNIQUES.values():
            lines.append(f"| {t['name_ko']} | {t['effectiveness']} | {t['use_case']} |")
        lines.extend(["", "## 분석 및 추천", "", analysis, "", "---",
                       "**참고**: Wei et al. 'CoT' (2022), Yao et al. 'ReAct' (2023)"])
        return "\n".join(lines)

    # ── 9. full: 전체 종합 리포트 (asyncio.gather 병렬) ──────

    async def _full_report(self, p: dict) -> str:
        model_name = p.get("model", "")
        use_case = p.get("use_case", "범용")

        if not model_name:
            return "\n".join([
                "### 종합 리포트 — 입력 필요:", "",
                "| 파라미터 | 설명 | 예시 |", "|---------|------|------|",
                "| model | 모델명 | Claude Sonnet 4.6, GPT-5.2 |",
                "| use_case | 용도 (선택) | 코드 생성, 고객 상담 |",
                "| monthly_tokens | 월간 토큰 (선택) | 10000000 |", "",
                "### 포함 항목 (6개 영역 병렬 분석):", "| # | 영역 | 내용 |", "|---|------|------|",
                "| 1 | HELM 평가 | 6차원 (정확성/견고성/보정성/공정성/효율성/안전성) |",
                "| 2 | 벤치마크 | MMLU, HumanEval, MT-Bench, Arena ELO, GSM8K, BBH |",
                "| 3 | 비용 | 토큰 단가, 캐싱/배치/라우팅 |",
                "| 4 | 안전성 | 할루시네이션, 편향, 유해성, 프라이버시 |",
                "| 5 | 배포 | Fine-tuning vs RAG vs Prompt Engineering |",
                "| 6 | 프롬프트 | CoT, Few-shot, ReAct, ToT |",
            ])

        # 6개 분석을 병렬 실행
        results = await asyncio.gather(
            self._evaluate_model({**p}),
            self._benchmark_analysis({**p}),
            self._cost_optimization({**p, "monthly_tokens": p.get("monthly_tokens", 10_000_000)}),
            self._safety_evaluation({**p}),
            self._deploy_strategy({**p, "use_case": use_case}),
            self._prompt_engineering({**p, "task_type": use_case}),
            return_exceptions=True,
        )

        titles = ["HELM 종합 평가", "벤치마크 분석", "비용 최적화", "안전성 평가", "배포 전략", "프롬프트 엔지니어링"]
        lines = [f"# AI 모델 전체 종합 리포트: {model_name}", "",
                  f"**용도**: {use_case} | **분석**: {len(titles)}개 영역 병렬", "", "---", ""]

        for i, (title, result) in enumerate(zip(titles, results), 1):
            lines.append(f"## Part {i}. {title}")
            lines.append("")
            if isinstance(result, Exception):
                lines.append(f"(오류: {result})")
                logger.error("full_report '%s' failed: %s", title, result)
            else:
                lines.append(str(result))
            lines.extend(["", "---", ""])

        lines.extend([
            "## 종합 의견", "",
            f"위 6개 영역 분석 결과, **{model_name}**은(는) '{use_case}' 용도에 대해 다각도 검증되었습니다.", "",
            "**학술 참고:**",
            "- Liang et al., 'Holistic Evaluation of Language Models' (Stanford CRFM, 2023)",
            "- Zheng et al., 'Judging LLM-as-a-Judge' (LMSYS, NeurIPS 2024)",
            "- OpenAI, 'GPT-4 Technical Report' (arXiv:2303.08774, 2023)",
            "- Bai et al., 'Constitutional AI' (Anthropic, arXiv:2212.08073, 2022)",
            "- Wei et al., 'Chain-of-Thought Prompting' (NeurIPS 2022)",
            "- Yao et al., 'ReAct: Synergizing Reasoning and Acting' (ICLR 2023)",
        ])
        return "\n".join(lines)
