"""
회의 효과성 분석 도구 (Meeting Effectiveness Tool) — 회의 비용, 품질, 문화를 정량 분석하여 최적화합니다.

학술 근거:
  - Rogelberg, Scott & Kello (2007) "The Science and Fiction of Meetings" — 회의 비용의 1.5x 기회비용 승수
  - Kauffeld & Lehmann-Willenbrock (2012) "Meetings Matter" — MeetingQuality Index (8차원)
  - Ringelmann Effect (1913) — 참여 인원 증가에 따른 개인 생산성 역비례
  - Allen, Lehmann-Willenbrock & Rogelberg (2015) — 회의 최적화 연구
  - Microsoft WorkLab (2022) — 주 23시간 회의, 비효율적 회의가 생산성 #1 장벽
  - Harvard Business Review (2017) — 관리자 주당 23시간, 72% 비효율 평가
  - Doodle State of Meetings Report (2019) — 무의미한 회의 비용 $541B/년(미국)

사용 방법:
  - action="cost"      : 회의 비용 계산 (참석자 급여 기반 + Rogelberg 1.5x 기회비용 승수)
  - action="score"     : MeetingQuality Index (8차원 가중 점수 — Kauffeld 2012 기반)
  - action="benchmark" : 회의 문화 벤치마크 (HBR/Doodle/Microsoft 데이터)
  - action="optimize"  : 최적 인원수 추천 (Ringelmann Effect 수식)
  - action="roi"       : 회의 ROI 분석
  - action="full"      : 위 5개 종합

필요 환경변수: 없음
필요 라이브러리: 없음 (순수 Python)
"""
from __future__ import annotations

import logging
import math
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.meeting_effectiveness")


# ═══════════════════════════════════════════════════════
#  유틸리티 함수
# ═══════════════════════════════════════════════════════

def _mean(vals: list) -> float:
    """리스트 평균값을 안전하게 계산합니다."""
    return sum(vals) / len(vals) if vals else 0.0


def _fmt_krw(amount: float) -> str:
    """금액을 한국 원화 형식으로 표시합니다."""
    if amount >= 1_0000_0000:
        return f"{amount / 1_0000_0000:,.1f}억원"
    elif amount >= 1_0000:
        return f"{amount / 1_0000:,.0f}만원"
    else:
        return f"{amount:,.0f}원"


def _fmt_pct(val: float) -> str:
    """퍼센트 형식으로 표시합니다."""
    return f"{val:.1f}%"


# ═══════════════════════════════════════════════════════
#  MeetingEffectivenessTool
# ═══════════════════════════════════════════════════════

class MeetingEffectivenessTool(BaseTool):
    """교수급 회의 효과성 분석 도구 — Rogelberg/Kauffeld/Ringelmann 이론 기반으로
    회의 비용, 품질 점수, 벤치마크, 인원 최적화, ROI를 정량 분석합니다."""

    # ── 직급별 연봉 기준 (만원 단위) ─────────────────
    # Rogelberg et al. (2007): 회의 비용 = 참석자 기회비용의 총합
    # 연봉 → 시급 변환: 연봉 / 2,080시간 (주 40시간 * 52주)
    HOURLY_RATES: dict[str, int] = {
        "intern": 25_000_000,       # 인턴: 연봉 2,500만원
        "staff": 45_000_000,        # 사원: 연봉 4,500만원
        "senior": 65_000_000,       # 대리/선임: 연봉 6,500만원
        "manager": 85_000_000,      # 과장/매니저: 연봉 8,500만원
        "director": 110_000_000,    # 부장/디렉터: 연봉 1억1,000만원
        "vp": 150_000_000,          # 이사/VP: 연봉 1억5,000만원
        "c_level": 200_000_000,     # C레벨 임원: 연봉 2억원
        "ceo": 300_000_000,         # CEO: 연봉 3억원
    }
    WORK_HOURS_PER_YEAR = 2_080  # 주 40시간 * 52주

    # ── Rogelberg 기회비용 승수 ──────────────────────
    # 회의에 참석하면 본래 업무를 못 하므로 실제 비용은 급여의 1.5배
    OPPORTUNITY_COST_MULTIPLIER = 1.5

    # ── Kauffeld (2012) MeetingQuality Index 8차원 가중치 ──
    QUALITY_DIMENSIONS: dict[str, dict] = {
        "clarity": {"name": "목적 명확성", "weight": 0.15,
                     "desc": "회의 목적과 안건이 사전에 명확히 공유되었는가"},
        "preparation": {"name": "사전 준비", "weight": 0.12,
                        "desc": "참석자들이 필요한 자료를 사전에 준비했는가"},
        "participation": {"name": "참여도", "weight": 0.15,
                          "desc": "모든 참석자가 적극적으로 발언하고 의견을 공유했는가"},
        "time_mgmt": {"name": "시간 관리", "weight": 0.13,
                      "desc": "정해진 시간 내에 안건을 모두 다뤘는가"},
        "decisions": {"name": "의사결정", "weight": 0.15,
                      "desc": "구체적인 결정이 내려졌는가 (결론 없이 끝나지 않았는가)"},
        "follow_up": {"name": "후속 조치", "weight": 0.12,
                      "desc": "담당자, 기한, 다음 단계가 명확히 정해졌는가"},
        "energy": {"name": "에너지/분위기", "weight": 0.08,
                   "desc": "참석자들의 집중도와 에너지 수준이 높았는가"},
        "relevance": {"name": "관련성", "weight": 0.10,
                      "desc": "모든 안건이 참석자 전원에게 관련이 있었는가"},
    }

    # ── 등급 체계 ──
    GRADE_THRESHOLDS = [
        (9.0, "S", "탁월 — 이 회의 방식을 전사 표준으로 삼을 것"),
        (7.0, "A", "우수 — 작은 개선점만 보완하면 됨"),
        (5.0, "B", "보통 — 구조적 개선이 필요함"),
        (3.0, "C", "미흡 — 회의 방식을 근본적으로 재설계할 것"),
        (0.0, "D", "폐지 검토 — 이 회의가 정말 필요한지 재검토"),
    ]

    # ── HBR/Doodle/Microsoft 벤치마크 데이터 ──────────
    MEETING_BENCHMARKS: dict[str, dict] = {
        "all_hands": {
            "name": "전체 회의 (All-Hands)",
            "optimal_duration": 60,
            "optimal_freq": "월1",
            "max_participants": 50,
            "purpose": "전사 방향 공유, 성과 축하, 문화 강화",
        },
        "team_standup": {
            "name": "팀 스탠드업",
            "optimal_duration": 15,
            "optimal_freq": "일1",
            "max_participants": 10,
            "purpose": "오늘 할 일, 어제 한 일, 장애물 공유",
        },
        "1on1": {
            "name": "1:1 미팅",
            "optimal_duration": 30,
            "optimal_freq": "주1",
            "max_participants": 2,
            "purpose": "코칭, 피드백, 경력 개발, 고민 상담",
        },
        "strategy": {
            "name": "전략 회의",
            "optimal_duration": 90,
            "optimal_freq": "주1",
            "max_participants": 8,
            "purpose": "장기 방향 설정, OKR 점검, 리스크 논의",
        },
        "brainstorm": {
            "name": "브레인스토밍",
            "optimal_duration": 45,
            "optimal_freq": "필요시",
            "max_participants": 12,
            "purpose": "아이디어 발산, 창의적 문제 해결",
        },
        "status_update": {
            "name": "현황 보고",
            "optimal_duration": 30,
            "optimal_freq": "주1",
            "max_participants": 15,
            "purpose": "프로젝트 진행 상황, 지표 공유",
        },
        "review": {
            "name": "리뷰/회고",
            "optimal_duration": 60,
            "optimal_freq": "격주1",
            "max_participants": 10,
            "purpose": "스프린트 회고, 코드 리뷰, 디자인 리뷰",
        },
        "training": {
            "name": "교육/워크숍",
            "optimal_duration": 120,
            "optimal_freq": "월1",
            "max_participants": 30,
            "purpose": "스킬 업, 지식 공유, 온보딩",
        },
    }

    # ── 메인 디스패처 ────────────────────────────────

    async def execute(self, **kwargs: Any) -> dict:
        action = kwargs.get("action", "full")

        actions = {
            "cost": self._cost,
            "score": self._score,
            "benchmark": self._benchmark,
            "optimize": self._optimize,
            "roi": self._roi,
            "full": self._full,
        }

        handler = actions.get(action)
        if handler:
            return await handler(kwargs)

        return {
            "status": "error",
            "message": (
                f"알 수 없는 action: {action}. "
                "cost, score, benchmark, optimize, roi, full 중 하나를 사용하세요."
            ),
        }

    # ═══════════════════════════════════════════════════
    #  1. 회의 비용 계산 (Cost)
    #  Rogelberg et al. (2007): 기회비용 승수 1.5x 적용
    # ═══════════════════════════════════════════════════

    async def _cost(self, params: dict) -> dict:
        """참석자 급여 기반 회의 비용을 계산합니다.

        입력:
          participants: [{"role": "manager", "count": 3}, {"role": "senior", "count": 5}]
          duration_hours: 1.5  (회의 시간)
          frequency_per_month: 4  (월간 회의 횟수)
        """
        participants = params.get("participants", [])
        duration_hours = float(params.get("duration_hours", 1.0))
        frequency = int(params.get("frequency_per_month", 1))

        if not participants:
            return {"status": "error", "message": "participants가 필요합니다. 예: [{\"role\":\"manager\",\"count\":3}]"}

        # ── 참석자별 시급 계산 ──
        cost_breakdown = []
        total_hourly = 0.0
        total_headcount = 0

        for p in participants:
            role = p.get("role", "staff")
            count = int(p.get("count", 1))
            annual_salary = self.HOURLY_RATES.get(role, self.HOURLY_RATES["staff"])
            hourly_rate = annual_salary / self.WORK_HOURS_PER_YEAR
            role_cost = hourly_rate * count

            cost_breakdown.append({
                "role": role,
                "count": count,
                "hourly_rate": round(hourly_rate),
                "subtotal_per_hour": round(role_cost),
            })
            total_hourly += role_cost
            total_headcount += count

        # ── Rogelberg 기회비용 적용 ──
        direct_cost_per_meeting = total_hourly * duration_hours
        opportunity_cost_per_meeting = direct_cost_per_meeting * self.OPPORTUNITY_COST_MULTIPLIER
        monthly_cost = opportunity_cost_per_meeting * frequency
        annual_cost = monthly_cost * 12

        # ── 비교 지표 ──
        avg_salary = _mean([self.HOURLY_RATES.get(p.get("role", "staff"), self.HOURLY_RATES["staff"]) for p in participants])
        # 이 회의 비용으로 고용할 수 있는 직원 수 (연봉 기준)
        hires_equivalent = annual_cost / avg_salary if avg_salary > 0 else 0

        result = {
            "participants_breakdown": cost_breakdown,
            "total_headcount": total_headcount,
            "duration_hours": duration_hours,
            "frequency_per_month": frequency,
            "direct_cost_per_meeting": round(direct_cost_per_meeting),
            "opportunity_cost_per_meeting": round(opportunity_cost_per_meeting),
            "monthly_cost": round(monthly_cost),
            "annual_cost": round(annual_cost),
            "opportunity_multiplier": self.OPPORTUNITY_COST_MULTIPLIER,
            "hires_equivalent": round(hires_equivalent, 1),
            "cost_display": {
                "per_meeting": _fmt_krw(opportunity_cost_per_meeting),
                "monthly": _fmt_krw(monthly_cost),
                "annual": _fmt_krw(annual_cost),
            },
        }

        # ── LLM 해석 ──
        prompt_data = (
            f"회의 비용 분석 결과:\n"
            f"- 참석자: {total_headcount}명 (직급 구성: {[p.get('role') for p in participants]})\n"
            f"- 시간: {duration_hours}시간, 월 {frequency}회\n"
            f"- 1회 비용 (기회비용 포함): {_fmt_krw(opportunity_cost_per_meeting)}\n"
            f"- 연간 비용: {_fmt_krw(annual_cost)}\n"
            f"- 동일 비용으로 고용 가능 인원: {hires_equivalent:.1f}명\n"
            f"- Rogelberg 기회비용 승수: {self.OPPORTUNITY_COST_MULTIPLIER}x 적용"
        )
        llm = await self._llm_call(
            system_prompt=(
                "당신은 조직 효율성 컨설턴트입니다. 회의 비용 분석 결과를 바탕으로:\n"
                "1. 이 비용이 적절한지 판단 (업계 평균 대비)\n"
                "2. 비용 절감 방안 3가지 구체적 제안\n"
                "3. 회의 시간 단축 or 빈도 줄이기 시 절감 효과 수치 계산\n"
                "한국어로 간결하고 실행 가능한 조언을 제공하세요."
            ),
            user_prompt=prompt_data,
        )
        result["llm_interpretation"] = llm
        return {"status": "success", "result": result}

    # ═══════════════════════════════════════════════════
    #  2. MeetingQuality Index (Score)
    #  Kauffeld & Lehmann-Willenbrock (2012): 8차원 가중 점수
    # ═══════════════════════════════════════════════════

    async def _score(self, params: dict) -> dict:
        """8차원 가중 점수로 회의 품질을 측정합니다.

        입력:
          scores: {"clarity": 8, "preparation": 6, "participation": 7, ...} (각 1~10)
          meeting_name: "주간 전략 회의" (선택)
        """
        scores = params.get("scores", {})
        meeting_name = params.get("meeting_name", "회의")

        if not scores:
            # 입력 없으면 차원 목록 안내
            dims_guide = []
            for key, dim in self.QUALITY_DIMENSIONS.items():
                dims_guide.append(f"  {key}: {dim['name']} — {dim['desc']}")
            return {
                "status": "error",
                "message": (
                    "scores가 필요합니다. 8개 차원에 각각 1~10점을 매겨주세요:\n"
                    + "\n".join(dims_guide)
                    + "\n\n예: scores={\"clarity\":8, \"preparation\":6, ...}"
                ),
            }

        # ── 차원별 가중 점수 계산 ──
        dimension_results = []
        weighted_sum = 0.0
        total_weight = 0.0
        raw_scores = []

        for key, dim in self.QUALITY_DIMENSIONS.items():
            raw = float(scores.get(key, 5))  # 미입력 시 5점 (보통)
            raw = max(1.0, min(10.0, raw))    # 1~10 범위 제한
            weighted = raw * dim["weight"]
            weighted_sum += weighted
            total_weight += dim["weight"]
            raw_scores.append(raw)

            dimension_results.append({
                "dimension": key,
                "name": dim["name"],
                "description": dim["desc"],
                "raw_score": raw,
                "weight": dim["weight"],
                "weighted_score": round(weighted, 2),
            })

        # 가중 평균 (10점 만점)
        overall = weighted_sum / total_weight if total_weight > 0 else 0

        # ── 등급 판정 ──
        grade = "D"
        grade_desc = "폐지 검토"
        for threshold, g, desc in self.GRADE_THRESHOLDS:
            if overall >= threshold:
                grade = g
                grade_desc = desc
                break

        # ── 강점/약점 분석 ──
        sorted_dims = sorted(dimension_results, key=lambda d: d["raw_score"], reverse=True)
        strengths = [d for d in sorted_dims[:2]]
        weaknesses = [d for d in sorted_dims[-2:]]

        result = {
            "meeting_name": meeting_name,
            "overall_score": round(overall, 2),
            "grade": grade,
            "grade_description": grade_desc,
            "dimensions": dimension_results,
            "strengths": [{"name": s["name"], "score": s["raw_score"]} for s in strengths],
            "weaknesses": [{"name": w["name"], "score": w["raw_score"]} for w in weaknesses],
            "raw_average": round(_mean(raw_scores), 2),
        }

        # ── LLM 해석 ──
        dim_text = "\n".join([
            f"  {d['name']}: {d['raw_score']}/10 (가중치 {d['weight']})"
            for d in dimension_results
        ])
        prompt_data = (
            f"'{meeting_name}' 품질 점수 분석:\n"
            f"- 종합: {overall:.1f}/10 (등급: {grade} — {grade_desc})\n"
            f"- 차원별:\n{dim_text}\n"
            f"- 강점: {', '.join([s['name'] for s in strengths])}\n"
            f"- 약점: {', '.join([w['name'] for w in weaknesses])}"
        )
        llm = await self._llm_call(
            system_prompt=(
                "당신은 Kauffeld & Lehmann-Willenbrock의 회의 품질 연구 전문가입니다.\n"
                "점수 분석 결과를 바탕으로:\n"
                "1. 가장 시급한 개선 포인트 2가지와 구체적 행동 지침\n"
                "2. 강점을 더 강화할 방법 1가지\n"
                "3. 다음 회의에서 즉시 적용 가능한 팁 2가지\n"
                "한국어로 간결하고 실행 가능한 조언을 제공하세요."
            ),
            user_prompt=prompt_data,
        )
        result["llm_interpretation"] = llm
        return {"status": "success", "result": result}

    # ═══════════════════════════════════════════════════
    #  3. 회의 문화 벤치마크 (Benchmark)
    #  HBR (2017) / Doodle (2019) / Microsoft WorkLab (2022) 데이터
    # ═══════════════════════════════════════════════════

    async def _benchmark(self, params: dict) -> dict:
        """현재 회의를 업계 최적 기준과 비교합니다.

        입력:
          meeting_type: "strategy" (8가지 중 택1)
          current_duration: 120  (현재 회의 시간, 분)
          current_freq: "주2"  (현재 빈도)
          current_participants: 15  (현재 참석자 수)
        """
        meeting_type = params.get("meeting_type", "")
        current_duration = int(params.get("current_duration", 60))
        current_freq = params.get("current_freq", "주1")
        current_participants = int(params.get("current_participants", 10))

        if meeting_type not in self.MEETING_BENCHMARKS:
            types_guide = "\n".join([
                f"  {k}: {v['name']} — {v['purpose']}"
                for k, v in self.MEETING_BENCHMARKS.items()
            ])
            return {
                "status": "error",
                "message": f"meeting_type이 필요합니다. 다음 중 택1:\n{types_guide}",
            }

        bench = self.MEETING_BENCHMARKS[meeting_type]
        optimal_dur = bench["optimal_duration"]
        optimal_freq = bench["optimal_freq"]
        max_part = bench["max_participants"]

        # ── 현재 vs 최적 비교 ──
        duration_diff = current_duration - optimal_dur
        duration_pct = (duration_diff / optimal_dur * 100) if optimal_dur > 0 else 0
        participant_diff = current_participants - max_part
        participant_pct = (participant_diff / max_part * 100) if max_part > 0 else 0

        # ── 건강도 점수 (간단 추정) ──
        health = 100.0
        if duration_diff > 0:
            health -= min(30, duration_pct * 0.5)  # 시간 초과 감점
        if participant_diff > 0:
            health -= min(30, participant_pct * 0.5)  # 인원 초과 감점
        health = max(0, min(100, health))

        comparisons = [
            {"metric": "시간 (분)", "current": current_duration, "optimal": optimal_dur,
             "diff": f"{'+' if duration_diff > 0 else ''}{duration_diff}분",
             "status": "적정" if abs(duration_diff) <= optimal_dur * 0.1 else ("초과" if duration_diff > 0 else "부족")},
            {"metric": "빈도", "current": current_freq, "optimal": optimal_freq,
             "diff": "-", "status": "비교 필요"},
            {"metric": "참석자 수", "current": current_participants, "optimal": f"최대 {max_part}명",
             "diff": f"{'+' if participant_diff > 0 else ''}{participant_diff}명",
             "status": "적정" if participant_diff <= 0 else "초과"},
        ]

        result = {
            "meeting_type": meeting_type,
            "meeting_name": bench["name"],
            "purpose": bench["purpose"],
            "comparisons": comparisons,
            "health_score": round(health, 1),
            "benchmark_source": "HBR (2017), Doodle (2019), Microsoft WorkLab (2022)",
        }

        # ── LLM 해석 ──
        comp_text = "\n".join([
            f"  {c['metric']}: 현재 {c['current']} vs 최적 {c['optimal']} ({c['status']})"
            for c in comparisons
        ])
        prompt_data = (
            f"'{bench['name']}' 벤치마크 비교:\n"
            f"- 목적: {bench['purpose']}\n"
            f"- 비교:\n{comp_text}\n"
            f"- 건강도: {health:.0f}/100"
        )
        llm = await self._llm_call(
            system_prompt=(
                "당신은 조직 효율성 전문가입니다. 회의 벤치마크 결과를 바탕으로:\n"
                "1. 현재 회의의 가장 큰 문제점 1가지\n"
                "2. 최적 기준에 맞추기 위한 구체적 3단계 행동 계획\n"
                "3. '이 회의를 없앨 수 있는가?' 관점에서 대안 제시 (비동기 문서, 슬랙 업데이트 등)\n"
                "한국어로 간결하고 실행 가능한 조언을 제공하세요."
            ),
            user_prompt=prompt_data,
        )
        result["llm_interpretation"] = llm
        return {"status": "success", "result": result}

    # ═══════════════════════════════════════════════════
    #  4. 최적 인원수 추천 (Optimize)
    #  Ringelmann Effect (1913): 개인효율 = 1 - 0.05*(n-1)
    # ═══════════════════════════════════════════════════

    async def _optimize(self, params: dict) -> dict:
        """Ringelmann Effect 기반 최적 인원수를 추천합니다.

        입력:
          meeting_purpose: "decision" | "brainstorm" | "info_sharing" | "review"
          current_participants: 15
          participant_names: ["김대표", "박이사", ...] (선택 — 필수/선택 분류용)
        """
        purpose = params.get("meeting_purpose", "decision")
        current_n = int(params.get("current_participants", 10))
        names = params.get("participant_names", [])

        # ── Ringelmann Effect 계산 ──
        # 개인 효율 = 1 - 0.05 * (n - 1), 최소 0.1
        ringelmann_data = []
        for n in range(1, max(current_n + 5, 16)):
            individual_eff = max(0.1, 1 - 0.05 * (n - 1))
            group_output = n * individual_eff  # 그룹 총 생산성
            ringelmann_data.append({
                "participants": n,
                "individual_efficiency": round(individual_eff * 100, 1),
                "group_output": round(group_output, 2),
            })

        # 현재 인원의 효율
        current_eff = max(0.1, 1 - 0.05 * (current_n - 1))

        # ── 목적별 최적 인원수 ──
        PURPOSE_OPTIMAL: dict[str, dict] = {
            "decision": {
                "name": "의사결정 회의",
                "optimal_range": (3, 7),
                "rule": "Jeff Bezos 2-pizza rule: 피자 2판으로 먹일 수 있는 인원 (≤8명)",
                "reasoning": "의사결정 속도는 인원수의 제곱에 반비례 (Allen & Rogelberg, 2015)",
            },
            "brainstorm": {
                "name": "브레인스토밍",
                "optimal_range": (4, 12),
                "rule": "다양한 관점 확보 + Ringelmann 효과 최소화",
                "reasoning": "아이디어 수는 12명까지 증가 후 포화 (Mullen et al., 1991)",
            },
            "info_sharing": {
                "name": "정보 전달/공유",
                "optimal_range": (1, 50),
                "rule": "인원 제한 불필요 (단방향 소통)",
                "reasoning": "전달형 회의는 인원 무관. 단, Q&A 시간은 최소화 (Microsoft, 2022)",
            },
            "review": {
                "name": "리뷰/회고",
                "optimal_range": (3, 10),
                "rule": "참여자 전원이 발언할 수 있는 규모",
                "reasoning": "10명 이상이면 개인 발언 시간 < 3분 (60분 기준) → 참여도 급감",
            },
        }

        purpose_info = PURPOSE_OPTIMAL.get(purpose, PURPOSE_OPTIMAL["decision"])
        opt_min, opt_max = purpose_info["optimal_range"]
        is_over = current_n > opt_max
        is_under = current_n < opt_min

        # ── 필수/선택 참석자 분류 추천 ──
        classification = None
        if names and current_n > opt_max:
            # 최적 인원 초과 시 분류 제안
            essential_count = min(opt_max, len(names))
            classification = {
                "essential_count": essential_count,
                "optional_count": len(names) - essential_count,
                "suggestion": f"핵심 {essential_count}명만 참석, 나머지는 회의록 공유로 대체",
            }

        result = {
            "meeting_purpose": purpose,
            "purpose_info": purpose_info,
            "current_participants": current_n,
            "current_individual_efficiency": _fmt_pct(current_eff * 100),
            "optimal_range": f"{opt_min}~{opt_max}명",
            "is_over_optimal": is_over,
            "is_under_optimal": is_under,
            "ringelmann_curve": ringelmann_data[:15],  # 최대 15명까지
            "classification": classification,
        }

        # ── LLM 해석 ──
        prompt_data = (
            f"회의 인원 최적화 분석:\n"
            f"- 목적: {purpose_info['name']}\n"
            f"- 현재 인원: {current_n}명 (개인 효율: {current_eff * 100:.0f}%)\n"
            f"- 최적 범위: {opt_min}~{opt_max}명\n"
            f"- 상태: {'인원 초과' if is_over else '인원 부족' if is_under else '적정'}\n"
            f"- Ringelmann 효과: 인원 1명 추가 시 개인 효율 5%p 감소\n"
            f"- {purpose_info['rule']}"
        )
        llm = await self._llm_call(
            system_prompt=(
                "당신은 Ringelmann Effect와 팀 다이내믹스 전문가입니다.\n"
                "인원 최적화 분석을 바탕으로:\n"
                "1. 현재 인원이 최적 범위를 벗어났다면 구체적 조정 방안\n"
                "2. 필수 참석자 vs 선택 참석자를 구분하는 기준 3가지\n"
                "3. '회의 없이 해결할 수 있는 안건'을 걸러내는 체크리스트\n"
                "한국어로 간결하고 실행 가능한 조언을 제공하세요."
            ),
            user_prompt=prompt_data,
        )
        result["llm_interpretation"] = llm
        return {"status": "success", "result": result}

    # ═══════════════════════════════════════════════════
    #  5. 회의 ROI 분석
    # ═══════════════════════════════════════════════════

    async def _roi(self, params: dict) -> dict:
        """회의에서 나온 의사결정의 가치 vs 비용을 비교합니다.

        입력:
          decisions_made: [{"description": "신제품 출시 결정", "estimated_value": 50000000}]
          meeting_cost: 500000  (cost action에서 계산한 1회 비용, 원)
          meeting_name: "전략 회의" (선택)
        """
        decisions = params.get("decisions_made", [])
        meeting_cost = float(params.get("meeting_cost", 0))
        meeting_name = params.get("meeting_name", "회의")

        if meeting_cost <= 0:
            return {
                "status": "error",
                "message": "meeting_cost가 필요합니다. cost action으로 먼저 비용을 계산하세요.",
            }

        # ── 의사결정 가치 합산 ──
        total_value = 0.0
        decision_details = []
        for d in decisions:
            val = float(d.get("estimated_value", 0))
            total_value += val
            decision_details.append({
                "description": d.get("description", "미정"),
                "estimated_value": round(val),
                "value_display": _fmt_krw(val),
            })

        # ── ROI 계산 ──
        # ROI = (가치 - 비용) / 비용 * 100
        roi_pct = ((total_value - meeting_cost) / meeting_cost * 100) if meeting_cost > 0 else 0
        net_value = total_value - meeting_cost

        # ── 건강 진단 ──
        if roi_pct >= 300:
            health = "매우 건강 — 회의 비용 대비 3배 이상 가치 창출"
        elif roi_pct >= 100:
            health = "건강 — 비용 이상의 가치를 창출함"
        elif roi_pct >= 0:
            health = "보통 — 손익분기. 효율 개선 필요"
        elif roi_pct >= -50:
            health = "경고 — 비용 대비 가치 부족. 회의 방식 재검토 필요"
        else:
            health = "위험 — 이 회의를 폐지하거나 근본적으로 재설계해야 함"

        # ── 의사결정 없는 회의 감지 ──
        if not decisions:
            health = "위험 — 의사결정이 0건. 이 회의에서 결정된 것이 없음"
            roi_pct = -100

        result = {
            "meeting_name": meeting_name,
            "meeting_cost": round(meeting_cost),
            "meeting_cost_display": _fmt_krw(meeting_cost),
            "decisions": decision_details,
            "decisions_count": len(decisions),
            "total_decision_value": round(total_value),
            "total_value_display": _fmt_krw(total_value),
            "net_value": round(net_value),
            "net_value_display": _fmt_krw(net_value),
            "roi_percent": round(roi_pct, 1),
            "health": health,
            "benchmark_roi": "건강한 ROI: 300%+ (1원 투자 시 4원 회수)",
        }

        # ── LLM 해석 ──
        dec_text = "\n".join([
            f"  - {d['description']}: {d['value_display']}"
            for d in decision_details
        ]) if decision_details else "  (의사결정 없음)"
        prompt_data = (
            f"'{meeting_name}' ROI 분석:\n"
            f"- 회의 비용: {_fmt_krw(meeting_cost)}\n"
            f"- 의사결정 {len(decisions)}건:\n{dec_text}\n"
            f"- 총 가치: {_fmt_krw(total_value)}\n"
            f"- ROI: {roi_pct:.0f}%\n"
            f"- 진단: {health}"
        )
        llm = await self._llm_call(
            system_prompt=(
                "당신은 회의 ROI 전문 컨설턴트입니다.\n"
                "ROI 분석 결과를 바탕으로:\n"
                "1. ROI가 낮다면 원인 분석 (비용이 높은가? 의사결정이 적은가?)\n"
                "2. ROI를 300%까지 올리기 위한 구체적 방안 3가지\n"
                "3. '회의 없이 의사결정할 수 있었던 건'을 식별하는 기준\n"
                "한국어로 간결하고 실행 가능한 조언을 제공하세요."
            ),
            user_prompt=prompt_data,
        )
        result["llm_interpretation"] = llm
        return {"status": "success", "result": result}

    # ═══════════════════════════════════════════════════
    #  6. 종합 분석 (Full)
    # ═══════════════════════════════════════════════════

    async def _full(self, params: dict) -> dict:
        """cost + score + benchmark + optimize + roi 5개를 종합 실행합니다."""
        results = {}
        actions = ["cost", "score", "benchmark", "optimize", "roi"]

        for act in actions:
            try:
                result = await getattr(self, f"_{act}")({**params, "action": act})
                results[act] = result
            except Exception as e:
                logger.warning("meeting_effectiveness full: %s action 실패 — %s", act, e)
                results[act] = {"status": "error", "message": str(e)}

        # ── 종합 LLM 요약 ──
        summaries = []
        for act, res in results.items():
            if res.get("status") == "success":
                r = res.get("result", {})
                if act == "cost":
                    summaries.append(f"비용: 1회 {r.get('cost_display', {}).get('per_meeting', 'N/A')}, 연간 {r.get('cost_display', {}).get('annual', 'N/A')}")
                elif act == "score":
                    summaries.append(f"품질: {r.get('overall_score', 'N/A')}/10 (등급: {r.get('grade', 'N/A')})")
                elif act == "benchmark":
                    summaries.append(f"벤치마크 건강도: {r.get('health_score', 'N/A')}/100")
                elif act == "optimize":
                    summaries.append(f"인원: 현재 {r.get('current_participants', 'N/A')}명, 최적 {r.get('optimal_range', 'N/A')}")
                elif act == "roi":
                    summaries.append(f"ROI: {r.get('roi_percent', 'N/A')}%")
            else:
                summaries.append(f"{act}: 분석 실패")

        prompt_data = "회의 종합 분석 결과:\n" + "\n".join([f"  - {s}" for s in summaries])
        llm = await self._llm_call(
            system_prompt=(
                "당신은 CEO 비서실 수석 컨설턴트입니다. 회의 종합 분석 결과를 바탕으로:\n"
                "1. 이 회의의 종합 건강도를 한 문장으로 진단\n"
                "2. 즉시 실행 가능한 TOP 3 개선 액션 (우선순위 순)\n"
                "3. 3개월 후 목표 상태 제시 (수치 포함)\n"
                "CEO가 바로 결정할 수 있도록 한국어로 간결하게 정리하세요."
            ),
            user_prompt=prompt_data,
        )

        return {
            "status": "success",
            "results": results,
            "llm_summary": llm,
        }
