"""
우선순위 매트릭스 도구 (Priority Matrix Tool) — 3가지 프레임워크로 업무 우선순위를 정량화합니다.

학술 근거:
  - Eisenhower Matrix (Covey 1989, "The 7 Habits of Highly Effective People")
    — 긴급성 x 중요도 4사분면 분류
  - RICE Scoring (Intercom, Sean McBride)
    — Reach x Impact x Confidence / Effort
  - WSJF — Weighted Shortest Job First (Reinertsen 2009, SAFe Framework)
    — Cost of Delay / Job Size
  - ICE Scoring — Impact x Confidence x Ease (비교 보조용)
  - Drucker (1967) "The Effective Executive" — CEO 시간 투자 원칙

사용 방법:
  - action="eisenhower"  : Eisenhower 4사분면 분류
  - action="rice"        : RICE 점수 계산
  - action="wsjf"        : WSJF 계산 (SAFe 방식)
  - action="compare"     : 3개 프레임워크 비교
  - action="time_invest" : CEO 시간 투자 분석 (Drucker 기반)
  - action="full"        : 위 5개 종합

필요 환경변수: 없음
필요 라이브러리: 없음 (순수 Python)
"""
from __future__ import annotations

import logging
import math
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.priority_matrix")


# ═══════════════════════════════════════════════════════
#  유틸리티 함수
# ═══════════════════════════════════════════════════════

def _mean(vals: list) -> float:
    """리스트 평균값을 안전하게 계산합니다."""
    return sum(vals) / len(vals) if vals else 0.0


def _rank_items(items: list[dict], score_key: str) -> list[dict]:
    """score_key 기준으로 내림차순 정렬하고 순위를 매깁니다."""
    sorted_items = sorted(items, key=lambda x: x.get(score_key, 0), reverse=True)
    for i, item in enumerate(sorted_items, 1):
        item["rank"] = i
    return sorted_items


# ═══════════════════════════════════════════════════════
#  PriorityMatrixTool
# ═══════════════════════════════════════════════════════

class PriorityMatrixTool(BaseTool):
    """교수급 우선순위 매트릭스 도구 — Eisenhower/RICE/WSJF 3가지 프레임워크로
    업무 우선순위를 정량화하고, CEO 시간 투자를 최적화합니다."""

    # ── Drucker (1967) 이상적 CEO 시간 배분 비율 ──
    DRUCKER_IDEAL: dict[str, dict] = {
        "strategy": {
            "name": "전략/비전",
            "ideal_pct": 30,
            "description": "장기 방향 설정, 시장 분석, 경쟁 전략, 비즈니스 모델 혁신",
        },
        "talent": {
            "name": "인재/조직",
            "ideal_pct": 25,
            "description": "채용, 코칭, 문화 구축, 핵심 인재 유지, 조직 설계",
        },
        "customer": {
            "name": "고객/시장",
            "ideal_pct": 20,
            "description": "고객 미팅, 파트너십, 시장 피드백, 브랜드 관리",
        },
        "execution": {
            "name": "실행/관리",
            "ideal_pct": 15,
            "description": "프로젝트 검토, 의사결정, 문제 해결, 프로세스 관리",
        },
        "personal": {
            "name": "개인 발전",
            "ideal_pct": 10,
            "description": "학습, 독서, 네트워킹, 건강 관리, 에너지 충전",
        },
    }

    # ── Eisenhower 4사분면 정의 ──
    QUADRANTS = {
        "Q1": {"name": "DO (즉시 실행)", "urgency": "긴급", "importance": "중요",
                "action": "직접 처리. 지금 당장 실행하세요."},
        "Q2": {"name": "PLAN (계획)", "urgency": "비긴급", "importance": "중요",
                "action": "일정에 넣고 계획적으로 실행. 가장 가치 있는 사분면."},
        "Q3": {"name": "DELEGATE (위임)", "urgency": "긴급", "importance": "비중요",
                "action": "다른 사람에게 위임하세요. CEO가 직접 할 필요 없음."},
        "Q4": {"name": "DELETE (삭제)", "urgency": "비긴급", "importance": "비중요",
                "action": "하지 마세요. 시간 낭비입니다."},
    }

    # ── RICE Impact 스케일 (Intercom 정의) ──
    RICE_IMPACT_SCALE = {
        3.0: "대규모 (Massive) — 전사적 영향",
        2.0: "큰 (High) — 부서/팀 전체에 영향",
        1.0: "보통 (Medium) — 일부에 영향",
        0.5: "작은 (Low) — 소수에 영향",
        0.25: "최소 (Minimal) — 거의 영향 없음",
    }

    # ── 메인 디스패처 ────────────────────────────────

    async def execute(self, **kwargs: Any) -> dict:
        action = kwargs.get("action", "full")

        actions = {
            "eisenhower": self._eisenhower,
            "rice": self._rice,
            "wsjf": self._wsjf,
            "compare": self._compare,
            "time_invest": self._time_invest,
            "full": self._full,
        }

        handler = actions.get(action)
        if handler:
            return await handler(kwargs)

        return {
            "status": "error",
            "message": (
                f"알 수 없는 action: {action}. "
                "eisenhower, rice, wsjf, compare, time_invest, full 중 하나를 사용하세요."
            ),
        }

    # ═══════════════════════════════════════════════════
    #  1. Eisenhower 4사분면 분류
    #  Covey (1989): 긴급성 x 중요도 매트릭스
    # ═══════════════════════════════════════════════════

    async def _eisenhower(self, params: dict) -> dict:
        """업무를 Eisenhower 4사분면으로 분류합니다.

        입력:
          tasks: [{"name": "전략 보고서", "urgency": 8, "importance": 9}, ...]
               urgency, importance: 각 1~10
        """
        tasks = params.get("tasks", [])
        if not tasks:
            return {
                "status": "error",
                "message": (
                    "tasks가 필요합니다. 예: "
                    "[{\"name\":\"전략 보고서\", \"urgency\":8, \"importance\":9}]"
                ),
            }

        # ── 사분면 분류 ──
        # 기준: urgency > 5 → 긴급, importance > 5 → 중요
        classified = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}
        task_details = []

        for t in tasks:
            name = t.get("name", "미정")
            urgency = float(t.get("urgency", 5))
            importance = float(t.get("importance", 5))
            urgency = max(1, min(10, urgency))
            importance = max(1, min(10, importance))

            is_urgent = urgency > 5
            is_important = importance > 5

            if is_urgent and is_important:
                quadrant = "Q1"
            elif not is_urgent and is_important:
                quadrant = "Q2"
            elif is_urgent and not is_important:
                quadrant = "Q3"
            else:
                quadrant = "Q4"

            detail = {
                "name": name,
                "urgency": urgency,
                "importance": importance,
                "quadrant": quadrant,
                "quadrant_name": self.QUADRANTS[quadrant]["name"],
                "action": self.QUADRANTS[quadrant]["action"],
            }
            classified[quadrant].append(detail)
            task_details.append(detail)

        # ── 사분면별 요약 ──
        quadrant_summary = {}
        for q_key, q_info in self.QUADRANTS.items():
            items = classified[q_key]
            quadrant_summary[q_key] = {
                "name": q_info["name"],
                "count": len(items),
                "tasks": [t["name"] for t in items],
                "action": q_info["action"],
            }

        # ── 시간 배분 진단 (Covey 권장: Q2에 가장 많은 시간) ──
        q2_ratio = len(classified["Q2"]) / len(tasks) * 100 if tasks else 0
        q1_ratio = len(classified["Q1"]) / len(tasks) * 100 if tasks else 0
        if q1_ratio > 50:
            time_diagnosis = "위기 모드 — Q1(긴급+중요)이 50%+ → 계획 부재. Q2 시간을 늘려야 함"
        elif q2_ratio >= 30:
            time_diagnosis = "건강 — Q2(계획적 중요 업무)가 30%+ → 장기 성과 극대화 중"
        elif q2_ratio >= 15:
            time_diagnosis = "보통 — Q2 비율이 더 높아져야 함"
        else:
            time_diagnosis = "경고 — Q2 비율 매우 낮음. 긴급한 것에만 끌려다니고 있음"

        result = {
            "total_tasks": len(tasks),
            "quadrant_summary": quadrant_summary,
            "task_details": task_details,
            "q2_ratio": round(q2_ratio, 1),
            "time_diagnosis": time_diagnosis,
        }

        # ── LLM 해석 ──
        q_text = "\n".join([
            f"  {q}: {s['count']}건 — {', '.join(s['tasks'][:3]) if s['tasks'] else '(없음)'}"
            for q, s in quadrant_summary.items()
        ])
        prompt_data = (
            f"Eisenhower 4사분면 분류 결과 ({len(tasks)}건):\n"
            f"{q_text}\n"
            f"- Q2 비율: {q2_ratio:.0f}%\n"
            f"- 진단: {time_diagnosis}"
        )
        llm = await self._llm_call(
            system_prompt=(
                "당신은 Stephen Covey의 시간 관리 전문가입니다.\n"
                "Eisenhower 분류 결과를 바탕으로:\n"
                "1. CEO가 이번 주에 집중해야 할 TOP 3 업무 (Q1 + Q2에서 선택)\n"
                "2. Q3(위임)에 있는 업무를 누구에게 어떻게 위임할지 구체적 방법\n"
                "3. Q4(삭제) 업무를 정말 삭제해도 되는지 리스크 체크\n"
                "4. Q2 비율을 높이기 위한 구체적 행동 2가지\n"
                "한국어로 간결하고 실행 가능한 조언을 제공하세요."
            ),
            user_prompt=prompt_data,
        )
        result["llm_interpretation"] = llm
        return {"status": "success", "result": result}

    # ═══════════════════════════════════════════════════
    #  2. RICE 점수 계산
    #  Intercom (Sean McBride): Reach x Impact x Confidence / Effort
    # ═══════════════════════════════════════════════════

    async def _rice(self, params: dict) -> dict:
        """RICE 점수로 업무 우선순위를 계산합니다.

        입력:
          tasks: [{
            "name": "모바일 앱 출시",
            "reach": 8,           # 영향 범위 (1~10, 몇 명/팀에 영향)
            "impact": 2.0,        # 영향 강도 (0.25/0.5/1.0/2.0/3.0)
            "confidence": 0.8,    # 확신도 (0.5=낮음/0.8=보통/1.0=높음)
            "effort_weeks": 4     # 소요 기간 (주)
          }, ...]
        """
        tasks = params.get("tasks", [])
        if not tasks:
            impact_guide = "\n".join([f"    {k}: {v}" for k, v in self.RICE_IMPACT_SCALE.items()])
            return {
                "status": "error",
                "message": (
                    "tasks가 필요합니다. 예:\n"
                    "[{\"name\":\"앱 출시\", \"reach\":8, \"impact\":2.0, \"confidence\":0.8, \"effort_weeks\":4}]\n\n"
                    f"Impact 스케일:\n{impact_guide}\n"
                    "Confidence: 0.5(낮음), 0.8(보통), 1.0(높음)"
                ),
            }

        # ── RICE 계산 ──
        scored = []
        for t in tasks:
            name = t.get("name", "미정")
            reach = float(t.get("reach", 5))
            impact = float(t.get("impact", 1.0))
            confidence = float(t.get("confidence", 0.8))
            effort = float(t.get("effort_weeks", 1))
            effort = max(0.1, effort)  # 0 방지

            rice_score = (reach * impact * confidence) / effort

            scored.append({
                "name": name,
                "reach": reach,
                "impact": impact,
                "impact_label": self.RICE_IMPACT_SCALE.get(impact, f"커스텀 ({impact})"),
                "confidence": confidence,
                "effort_weeks": effort,
                "rice_score": round(rice_score, 2),
            })

        # 순위 매기기
        scored = _rank_items(scored, "rice_score")

        # ── 상위 3개 추천 ──
        top3 = scored[:3]

        result = {
            "total_tasks": len(tasks),
            "ranked_tasks": scored,
            "top3_priority": [{"rank": t["rank"], "name": t["name"], "score": t["rice_score"]} for t in top3],
            "score_range": {
                "max": scored[0]["rice_score"] if scored else 0,
                "min": scored[-1]["rice_score"] if scored else 0,
                "spread": round(scored[0]["rice_score"] - scored[-1]["rice_score"], 2) if len(scored) > 1 else 0,
            },
        }

        # ── LLM 해석 ──
        rank_text = "\n".join([
            f"  #{t['rank']}: {t['name']} (RICE={t['rice_score']}) — R:{t['reach']} I:{t['impact']} C:{t['confidence']} E:{t['effort_weeks']}주"
            for t in scored[:5]
        ])
        prompt_data = (
            f"RICE 점수 분석 ({len(tasks)}건):\n"
            f"상위 5개:\n{rank_text}\n"
            f"최고 점수: {result['score_range']['max']}, 최저 점수: {result['score_range']['min']}"
        )
        llm = await self._llm_call(
            system_prompt=(
                "당신은 RICE 프레임워크(Intercom) 전문가입니다.\n"
                "RICE 점수 분석 결과를 바탕으로:\n"
                "1. 상위 3개를 '이번 분기 필수 실행'으로 추천하되, 실행 순서와 이유 설명\n"
                "2. Confidence가 낮은 항목에 대해 '확신도를 높이는 방법' (사용자 인터뷰, MVP 테스트 등)\n"
                "3. Effort 대비 Impact가 높은 '퀵윈(Quick Win)' 항목 1~2개 선별\n"
                "한국어로 간결하고 실행 가능한 조언을 제공하세요."
            ),
            user_prompt=prompt_data,
        )
        result["llm_interpretation"] = llm
        return {"status": "success", "result": result}

    # ═══════════════════════════════════════════════════
    #  3. WSJF 계산 (SAFe)
    #  Reinertsen (2009): Cost of Delay / Job Size
    # ═══════════════════════════════════════════════════

    async def _wsjf(self, params: dict) -> dict:
        """WSJF로 업무 우선순위를 계산합니다.

        입력:
          tasks: [{
            "name": "결제 시스템 개선",
            "user_value": 8,         # 사용자/비즈니스 가치 (1~10)
            "time_criticality": 7,   # 시간 민감도 (1~10, 늦을수록 가치 감소)
            "risk_reduction": 6,     # 리스크/기회 감소 (1~10)
            "job_size": 5            # 작업 규모 (1~10, 10=매우 큼)
          }, ...]
        """
        tasks = params.get("tasks", [])
        if not tasks:
            return {
                "status": "error",
                "message": (
                    "tasks가 필요합니다. 예:\n"
                    "[{\"name\":\"결제 개선\", \"user_value\":8, \"time_criticality\":7, "
                    "\"risk_reduction\":6, \"job_size\":5}]"
                ),
            }

        # ── WSJF 계산 ──
        scored = []
        for t in tasks:
            name = t.get("name", "미정")
            user_value = float(t.get("user_value", 5))
            time_crit = float(t.get("time_criticality", 5))
            risk_red = float(t.get("risk_reduction", 5))
            job_size = float(t.get("job_size", 5))
            job_size = max(1, job_size)  # 0 방지

            cost_of_delay = user_value + time_crit + risk_red
            wsjf_score = cost_of_delay / job_size

            scored.append({
                "name": name,
                "user_value": user_value,
                "time_criticality": time_crit,
                "risk_reduction": risk_red,
                "cost_of_delay": round(cost_of_delay, 1),
                "job_size": job_size,
                "wsjf_score": round(wsjf_score, 2),
            })

        scored = _rank_items(scored, "wsjf_score")

        # ── 지연 비용 분석 ──
        high_cod = [t for t in scored if t["cost_of_delay"] > 20]
        small_jobs = [t for t in scored if t["job_size"] <= 3]

        result = {
            "total_tasks": len(tasks),
            "ranked_tasks": scored,
            "high_cost_of_delay": [{"name": t["name"], "cod": t["cost_of_delay"]} for t in high_cod],
            "quick_wins": [{"name": t["name"], "size": t["job_size"], "wsjf": t["wsjf_score"]} for t in small_jobs[:3]],
        }

        # ── LLM 해석 ──
        rank_text = "\n".join([
            f"  #{t['rank']}: {t['name']} (WSJF={t['wsjf_score']}) — CoD:{t['cost_of_delay']} / Size:{t['job_size']}"
            for t in scored[:5]
        ])
        prompt_data = (
            f"WSJF 분석 ({len(tasks)}건):\n"
            f"상위 5개:\n{rank_text}\n"
            f"지연 비용 높은 항목: {len(high_cod)}건\n"
            f"Quick Win 후보: {len(small_jobs)}건"
        )
        llm = await self._llm_call(
            system_prompt=(
                "당신은 SAFe/Lean 프레임워크 전문가입니다.\n"
                "WSJF 분석 결과를 바탕으로:\n"
                "1. WSJF 최상위 3개를 '지금 시작해야 하는 이유' 설명\n"
                "2. Cost of Delay가 높은 항목 중 '1주일 지연 시 손실액' 추정\n"
                "3. Job Size를 줄일 수 있는 분할 방법 제안 (MVP, 단계별 릴리스 등)\n"
                "한국어로 간결하고 실행 가능한 조언을 제공하세요."
            ),
            user_prompt=prompt_data,
        )
        result["llm_interpretation"] = llm
        return {"status": "success", "result": result}

    # ═══════════════════════════════════════════════════
    #  4. 3개 프레임워크 비교 (Compare)
    # ═══════════════════════════════════════════════════

    async def _compare(self, params: dict) -> dict:
        """동일한 업무를 Eisenhower + RICE + WSJF 3개로 분석하고 비교합니다.

        입력:
          tasks: [{
            "name": "신규 기능 개발",
            "urgency": 7, "importance": 9,                          # Eisenhower
            "reach": 8, "impact": 2.0, "confidence": 0.8, "effort_weeks": 4,  # RICE
            "user_value": 8, "time_criticality": 7, "risk_reduction": 6, "job_size": 5  # WSJF
          }, ...]
        """
        tasks = params.get("tasks", [])
        if not tasks:
            return {
                "status": "error",
                "message": "tasks가 필요합니다. Eisenhower/RICE/WSJF 파라미터를 모두 포함해주세요.",
            }

        # ── 3개 프레임워크 각각 실행 (내부 호출) ──
        eisen_result = await self._eisenhower(params)
        rice_result = await self._rice(params)
        wsjf_result = await self._wsjf(params)

        # ── 순위 추출 ──
        eisen_tasks = eisen_result.get("result", {}).get("task_details", [])
        rice_tasks = rice_result.get("result", {}).get("ranked_tasks", [])
        wsjf_tasks = wsjf_result.get("result", {}).get("ranked_tasks", [])

        # Eisenhower 순위: Q1 > Q2 > Q3 > Q4, 같은 사분면이면 urgency+importance 합산
        q_order = {"Q1": 0, "Q2": 1, "Q3": 2, "Q4": 3}
        eisen_sorted = sorted(
            eisen_tasks,
            key=lambda t: (q_order.get(t.get("quadrant", "Q4"), 4), -(t.get("urgency", 0) + t.get("importance", 0)))
        )
        for i, t in enumerate(eisen_sorted, 1):
            t["eisenhower_rank"] = i

        # ── 업무별 3개 순위 합산 → 합의 점수 ──
        comparisons = []
        for task in tasks:
            name = task.get("name", "미정")

            # 각 프레임워크에서 이 업무의 순위 찾기
            e_rank = next((t["eisenhower_rank"] for t in eisen_sorted if t["name"] == name), len(tasks))
            r_rank = next((t["rank"] for t in rice_tasks if t["name"] == name), len(tasks))
            w_rank = next((t["rank"] for t in wsjf_tasks if t["name"] == name), len(tasks))

            avg_rank = (e_rank + r_rank + w_rank) / 3.0
            rank_spread = max(e_rank, r_rank, w_rank) - min(e_rank, r_rank, w_rank)

            comparisons.append({
                "name": name,
                "eisenhower_rank": e_rank,
                "rice_rank": r_rank,
                "wsjf_rank": w_rank,
                "consensus_rank": round(avg_rank, 1),
                "rank_spread": rank_spread,
                "disagreement": rank_spread >= 3,  # 3단계 이상 차이나면 불일치
            })

        # 합의 순위로 정렬
        comparisons = sorted(comparisons, key=lambda x: x["consensus_rank"])
        for i, c in enumerate(comparisons, 1):
            c["final_rank"] = i

        disagreements = [c for c in comparisons if c["disagreement"]]

        result = {
            "total_tasks": len(tasks),
            "comparisons": comparisons,
            "disagreements": disagreements,
            "framework_results": {
                "eisenhower": eisen_result.get("result", {}),
                "rice": rice_result.get("result", {}),
                "wsjf": wsjf_result.get("result", {}),
            },
        }

        # ── LLM 해석 ──
        comp_text = "\n".join([
            f"  #{c['final_rank']}: {c['name']} — E:{c['eisenhower_rank']} R:{c['rice_rank']} W:{c['wsjf_rank']} "
            f"(합의:{c['consensus_rank']:.1f}){' [불일치]' if c['disagreement'] else ''}"
            for c in comparisons[:5]
        ])
        disagree_text = "\n".join([
            f"  - {d['name']}: E:{d['eisenhower_rank']} vs R:{d['rice_rank']} vs W:{d['wsjf_rank']} (차이: {d['rank_spread']})"
            for d in disagreements
        ]) if disagreements else "  (없음)"

        prompt_data = (
            f"3개 프레임워크 비교 ({len(tasks)}건):\n"
            f"합의 순위:\n{comp_text}\n\n"
            f"불일치 항목:\n{disagree_text}"
        )
        llm = await self._llm_call(
            system_prompt=(
                "당신은 전략적 우선순위 설정 전문가입니다.\n"
                "3개 프레임워크(Eisenhower/RICE/WSJF) 비교 결과를 바탕으로:\n"
                "1. 합의 상위 3개를 '이번 주 집중 업무'로 확정하고 이유 설명\n"
                "2. 불일치 항목에 대해 '어떤 프레임워크를 신뢰해야 하는지' 판단 기준 제시\n"
                "3. CEO에게 '이 순서로 하세요'라고 말할 수 있는 최종 추천 리스트\n"
                "한국어로 간결하고 실행 가능한 조언을 제공하세요."
            ),
            user_prompt=prompt_data,
        )
        result["llm_interpretation"] = llm
        return {"status": "success", "result": result}

    # ═══════════════════════════════════════════════════
    #  5. CEO 시간 투자 분석 (Time Invest)
    #  Drucker (1967): 효과적 경영자의 시간 관리
    # ═══════════════════════════════════════════════════

    async def _time_invest(self, params: dict) -> dict:
        """CEO의 현재 시간 배분을 Drucker 이상 비율과 비교합니다.

        입력:
          current_time_allocation: {
            "strategy": 10,    # 주당 시간
            "talent": 5,
            "customer": 8,
            "execution": 20,
            "personal": 2
          }
          total_work_hours: 50  (주당 총 근무시간, 선택)
        """
        allocation = params.get("current_time_allocation", {})
        total_hours = float(params.get("total_work_hours", 0))

        if not allocation:
            cats_guide = "\n".join([
                f"  {k}: {v['name']} — {v['description']} (이상: {v['ideal_pct']}%)"
                for k, v in self.DRUCKER_IDEAL.items()
            ])
            return {
                "status": "error",
                "message": (
                    "current_time_allocation이 필요합니다 (주당 시간). 예:\n"
                    "{\"strategy\":10, \"talent\":5, \"customer\":8, \"execution\":20, \"personal\":2}\n\n"
                    f"카테고리:\n{cats_guide}"
                ),
            }

        # ── 시간 합산 및 비율 계산 ──
        if total_hours <= 0:
            total_hours = sum(allocation.values())
        if total_hours <= 0:
            total_hours = 50  # 기본값

        gap_analysis = []
        total_gap = 0.0

        for cat_key, cat_info in self.DRUCKER_IDEAL.items():
            current_hours = float(allocation.get(cat_key, 0))
            current_pct = (current_hours / total_hours * 100) if total_hours > 0 else 0
            ideal_pct = cat_info["ideal_pct"]
            gap = current_pct - ideal_pct
            ideal_hours = total_hours * ideal_pct / 100

            status = "적정"
            if gap > 10:
                status = "과다 투자"
            elif gap > 5:
                status = "약간 초과"
            elif gap < -10:
                status = "심각한 부족"
            elif gap < -5:
                status = "부족"

            total_gap += abs(gap)

            gap_analysis.append({
                "category": cat_key,
                "name": cat_info["name"],
                "description": cat_info["description"],
                "current_hours": current_hours,
                "current_pct": round(current_pct, 1),
                "ideal_pct": ideal_pct,
                "ideal_hours": round(ideal_hours, 1),
                "gap_pct": round(gap, 1),
                "gap_hours": round(current_hours - ideal_hours, 1),
                "status": status,
            })

        # ── 종합 진단 ──
        avg_gap = total_gap / len(self.DRUCKER_IDEAL) if self.DRUCKER_IDEAL else 0
        if avg_gap < 5:
            overall_diagnosis = "우수 — Drucker 이상 배분에 가까움"
        elif avg_gap < 10:
            overall_diagnosis = "보통 — 일부 카테고리 조정 필요"
        elif avg_gap < 20:
            overall_diagnosis = "주의 — 시간 배분이 상당히 불균형"
        else:
            overall_diagnosis = "경고 — 시간 배분을 근본적으로 재설계해야 함"

        # ── 가장 큰 GAP (조정 필요) ──
        biggest_gaps = sorted(gap_analysis, key=lambda x: abs(x["gap_pct"]), reverse=True)[:3]

        result = {
            "total_work_hours": total_hours,
            "gap_analysis": gap_analysis,
            "overall_diagnosis": overall_diagnosis,
            "avg_gap": round(avg_gap, 1),
            "biggest_gaps": [{"name": g["name"], "gap": g["gap_pct"], "status": g["status"]} for g in biggest_gaps],
            "reference": "Drucker (1967) 'The Effective Executive'",
        }

        # ── LLM 해석 ──
        gap_text = "\n".join([
            f"  {g['name']}: 현재 {g['current_pct']:.0f}% vs 이상 {g['ideal_pct']}% (GAP: {g['gap_pct']:+.0f}%p) — {g['status']}"
            for g in gap_analysis
        ])
        prompt_data = (
            f"CEO 시간 투자 분석 (주 {total_hours}시간):\n"
            f"{gap_text}\n"
            f"- 종합: {overall_diagnosis}\n"
            f"- 평균 GAP: {avg_gap:.0f}%p"
        )
        llm = await self._llm_call(
            system_prompt=(
                "당신은 Peter Drucker의 'The Effective Executive' 전문가입니다.\n"
                "CEO 시간 배분 분석을 바탕으로:\n"
                "1. 가장 과다 투자된 영역에서 시간을 빼는 구체적 방법 (위임, 자동화, 폐지)\n"
                "2. 가장 부족한 영역에 시간을 확보하는 구체적 방법\n"
                "3. '이번 주부터 바꿀 수 있는 것' 1가지 (작은 변화부터)\n"
                "4. 3개월 후 이상적 시간 배분 목표\n"
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
        """eisenhower + rice + wsjf + compare + time_invest 5개를 종합 실행합니다."""
        results = {}
        actions = ["eisenhower", "rice", "wsjf", "compare", "time_invest"]

        for act in actions:
            try:
                result = await getattr(self, f"_{act}")({**params, "action": act})
                results[act] = result
            except Exception as e:
                logger.warning("priority_matrix full: %s action 실패 — %s", act, e)
                results[act] = {"status": "error", "message": str(e)}

        # ── 종합 LLM 요약 ──
        summaries = []
        for act, res in results.items():
            if res.get("status") == "success":
                r = res.get("result", {})
                if act == "eisenhower":
                    qs = r.get("quadrant_summary", {})
                    summaries.append(f"Eisenhower: Q1={qs.get('Q1', {}).get('count', 0)}건, Q2={qs.get('Q2', {}).get('count', 0)}건")
                elif act == "rice":
                    top = r.get("top3_priority", [])
                    summaries.append(f"RICE 상위: {', '.join([t['name'] for t in top[:2]])}" if top else "RICE: 데이터 없음")
                elif act == "wsjf":
                    ranked = r.get("ranked_tasks", [])
                    summaries.append(f"WSJF 1위: {ranked[0]['name']}(점수:{ranked[0]['wsjf_score']})" if ranked else "WSJF: 데이터 없음")
                elif act == "compare":
                    comps = r.get("comparisons", [])
                    summaries.append(f"합의 1위: {comps[0]['name']}" if comps else "비교: 데이터 없음")
                elif act == "time_invest":
                    summaries.append(f"시간배분: {r.get('overall_diagnosis', 'N/A')}")
            else:
                summaries.append(f"{act}: 분석 실패")

        prompt_data = "우선순위 종합 분석 결과:\n" + "\n".join([f"  - {s}" for s in summaries])
        llm = await self._llm_call(
            system_prompt=(
                "당신은 CEO 비서실 수석 전략 고문입니다.\n"
                "5개 프레임워크 종합 분석을 바탕으로:\n"
                "1. CEO가 이번 주에 집중해야 할 TOP 3 업무 (최종 확정)\n"
                "2. 시간 배분 조정이 필요하다면 구체적 변경 사항\n"
                "3. '하지 말아야 할 것' TOP 2 (시간 절약)\n"
                "CEO가 1분 안에 읽고 결정할 수 있도록 한국어로 간결하게 정리하세요."
            ),
            user_prompt=prompt_data,
        )

        return {
            "status": "success",
            "results": results,
            "llm_summary": llm,
        }
