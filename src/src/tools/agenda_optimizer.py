"""
안건/아젠다 최적화 도구 (Agenda Optimizer) — 회의 안건을 최적 순서로 배치하고 시간 배분합니다.

비서실 전용 도구로, 회의 효율을 극대화하기 위해 학술 연구 기반의
에너지 곡선, 시간 배분, 퍼실리테이션 기법을 적용합니다.

학술 근거:
  - Allen, Lehmann-Willenbrock & Rogelberg (2015) "An Agenda to Make Meetings Work"
  - Schwarz (2017) "The Skilled Facilitator" — 퍼실리테이션 원칙
  - Kahneman & Tversky (1979) — Peak-End Rule (회의 인상은 최고점과 끝)
  - Parkinson's Law (1955) — 시간이 있으면 그만큼 채운다
  - Circadian Rhythm Research — 시간대별 인지능력 변화

사용 방법:
  - action="sequence"   : 안건 최적 순서 배치 (에너지·복잡도 기반)
  - action="timeboxing" : 시간 배분 최적화 (Parkinson 보정)
  - action="energy"     : 에너지 곡선 매핑 (일주기 + 회의 내 피로도)
  - action="facilitate" : 퍼실리테이션 가이드 생성 (Schwarz 기반)
  - action="template"   : 회의 유형별 아젠다 템플릿 생성
  - action="full"       : 위 5개 종합 분석

필요 환경변수: 없음
필요 라이브러리: 없음 (순수 Python)
"""
from __future__ import annotations

import logging
import math
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.agenda_optimizer")


# ═══════════════════════════════════════════════════════
#  유틸리티 함수
# ═══════════════════════════════════════════════════════

def _mean(vals: list) -> float:
    """리스트 평균 (빈 리스트 방어)."""
    return sum(vals) / len(vals) if vals else 0.0


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """값을 범위 내로 고정."""
    return max(lo, min(hi, value))


def _parse_time(time_str: str) -> tuple[int, int]:
    """'HH:MM' 문자열을 (hour, minute) 튜플로 변환."""
    parts = time_str.strip().split(":")
    return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0


def _add_minutes(hour: int, minute: int, add_min: int) -> tuple[int, int]:
    """시각에 분을 더한 결과를 (hour, minute) 튜플로 반환."""
    total = hour * 60 + minute + add_min
    return total // 60, total % 60


def _format_time(hour: int, minute: int) -> str:
    """(hour, minute) → 'HH:MM' 문자열."""
    return f"{hour:02d}:{minute:02d}"


# ═══════════════════════════════════════════════════════
#  AgendaOptimizerTool
# ═══════════════════════════════════════════════════════

class AgendaOptimizerTool(BaseTool):
    """교수급 안건 최적화 도구 — 순서·시간·에너지·퍼실리테이션·템플릿 5가지 분석.

    Allen(2015)의 회의 효율 연구, Schwarz(2017) 퍼실리테이션 이론,
    Kahneman의 Peak-End Rule, Parkinson's Law 등을 종합 적용합니다.
    """

    # ── 일주기(Circadian) 에너지 곡선 (시간 → 상대 에너지, 0~1) ──
    CIRCADIAN_ENERGY: dict[str, float] = {
        "07:00": 0.55, "08:00": 0.65, "09:00": 0.70, "10:00": 0.90,
        "11:00": 1.00, "12:00": 0.60, "13:00": 0.50, "14:00": 0.70,
        "15:00": 0.85, "16:00": 0.80, "17:00": 0.65, "18:00": 0.50,
        "19:00": 0.45, "20:00": 0.40,
    }

    # ── 안건 유형별 최적 배치 우선순위 (낮을수록 앞으로) ──
    TYPE_PRIORITY: dict[str, int] = {
        "decision": 1,      # 의사결정 → 회의 초반 (인지 에너지 최고)
        "discussion": 2,    # 토론 → 초~중반
        "brainstorm": 3,    # 브레인스토밍 → 중반 (워밍업 후)
        "info": 4,          # 정보 공유 → 후반 (에너지 낮아도 가능)
    }

    # ── 안건 유형별 에너지 소모 계수 ──
    TYPE_ENERGY_DRAIN: dict[str, float] = {
        "decision": 1.5,    # 의사결정은 에너지 소모 최대
        "discussion": 1.2,
        "brainstorm": 1.0,
        "info": 0.5,        # 정보 공유는 에너지 소모 최소
    }

    # ── 퍼실리테이션 기법 사전 (Schwarz 2017) ──
    FACILITATION_TECHNIQUES: dict[str, list[dict[str, str]]] = {
        "decision": [
            {"name": "Gradients of Agreement", "desc": "1~5단계 동의 수준으로 합의 도출 (흑백 투표 대신 그라디언트)"},
            {"name": "Fist of Five", "desc": "주먹(1)~다섯 손가락(5)으로 동의 수준 표시, 빠른 합의 확인"},
            {"name": "Decision Matrix", "desc": "기준×옵션 행렬로 점수화하여 객관적 의사결정"},
        ],
        "discussion": [
            {"name": "Round Robin", "desc": "순서대로 발언 — 소수 독점 방지, 전원 참여 보장"},
            {"name": "Think-Pair-Share", "desc": "개인 생각 → 짝 토론 → 전체 공유 (내성적 참가자 참여↑)"},
            {"name": "Fishbowl", "desc": "안쪽 원이 토론, 바깥 원이 관찰 → 교대 (대규모 토론에 효과적)"},
        ],
        "brainstorm": [
            {"name": "Brainwriting 6-3-5", "desc": "6명이 3개 아이디어를 5분마다 돌려쓰기 (30분에 108개 아이디어)"},
            {"name": "Reverse Brainstorm", "desc": "문제를 악화시키는 방법 먼저 → 그 반대가 해결책 (창의적 전환)"},
            {"name": "SCAMPER", "desc": "대체·결합·적용·수정·용도변경·제거·뒤집기 7가지 관점 발상"},
        ],
        "info": [
            {"name": "Parking Lot", "desc": "본 안건과 무관한 질문은 '주차장'에 메모 → 나중에 처리"},
            {"name": "Q&A Timebox", "desc": "질문 시간을 명확히 제한 (무한 질문 방지)"},
            {"name": "One-Page Summary", "desc": "사전 배포 요약본 → 회의에서는 Q&A만 (발표 시간 절약)"},
        ],
    }

    # ── 회의 유형별 표준 템플릿 ──
    MEETING_TEMPLATES: dict[str, dict] = {
        "weekly_team": {
            "name_ko": "주간 팀 회의",
            "sections": [
                {"title": "체크인/근황 공유", "pct": 0.11, "type": "info", "purpose": "팀 분위기 파악, 아이스브레이킹"},
                {"title": "지난주 성과 리뷰", "pct": 0.22, "type": "info", "purpose": "완료 항목 확인, 성과 인정"},
                {"title": "이번 주 핵심 계획", "pct": 0.33, "type": "discussion", "purpose": "우선순위 합의, 역할 분배"},
                {"title": "이슈/블로커 논의", "pct": 0.23, "type": "decision", "purpose": "장애물 해결, 즉시 의사결정"},
                {"title": "마무리/액션 아이템 정리", "pct": 0.11, "type": "info", "purpose": "다음 단계 명확화, 긍정 마무리(Peak-End)"},
            ],
        },
        "monthly_review": {
            "name_ko": "월간 리뷰 회의",
            "sections": [
                {"title": "월간 KPI/목표 달성률", "pct": 0.20, "type": "info", "purpose": "데이터 기반 성과 공유"},
                {"title": "핵심 성과 분석", "pct": 0.25, "type": "discussion", "purpose": "성공/실패 요인 분석"},
                {"title": "다음 달 전략 논의", "pct": 0.25, "type": "decision", "purpose": "방향 조정, 자원 재배분"},
                {"title": "팀 피드백/건의", "pct": 0.15, "type": "discussion", "purpose": "바텀업 의견 수렴"},
                {"title": "다음 달 액션 플랜 확정", "pct": 0.15, "type": "decision", "purpose": "구체적 실행 계획(Peak-End)"},
            ],
        },
        "strategy": {
            "name_ko": "전략 회의",
            "sections": [
                {"title": "현황 브리핑 (데이터/시장)", "pct": 0.15, "type": "info", "purpose": "공통 맥락 구축"},
                {"title": "핵심 이슈 정의", "pct": 0.15, "type": "discussion", "purpose": "해결할 문제 명확화"},
                {"title": "전략 옵션 브레인스토밍", "pct": 0.25, "type": "brainstorm", "purpose": "다양한 대안 도출"},
                {"title": "옵션 평가 및 선택", "pct": 0.25, "type": "decision", "purpose": "기준 기반 최종 결정"},
                {"title": "실행 로드맵 확정", "pct": 0.20, "type": "decision", "purpose": "담당자·일정·마일스톤(Peak-End)"},
            ],
        },
        "1on1": {
            "name_ko": "1:1 면담",
            "sections": [
                {"title": "안부/최근 상태", "pct": 0.15, "type": "info", "purpose": "라포(신뢰) 형성"},
                {"title": "진행 중인 업무 점검", "pct": 0.25, "type": "discussion", "purpose": "현황 공유, 블로커 파악"},
                {"title": "성장/커리어 대화", "pct": 0.25, "type": "discussion", "purpose": "장기 목표 정렬"},
                {"title": "피드백 교환 (쌍방향)", "pct": 0.20, "type": "discussion", "purpose": "개선점 공유 (매니저↔팀원)"},
                {"title": "다음 액션 정리", "pct": 0.15, "type": "info", "purpose": "명확한 다음 단계(Peak-End)"},
            ],
        },
        "kickoff": {
            "name_ko": "프로젝트 킥오프",
            "sections": [
                {"title": "프로젝트 배경/목적", "pct": 0.15, "type": "info", "purpose": "왜 하는지 전원 이해"},
                {"title": "목표/성공 기준(KPI)", "pct": 0.15, "type": "decision", "purpose": "측정 가능한 목표 합의"},
                {"title": "범위/산출물 정의", "pct": 0.20, "type": "discussion", "purpose": "포함/제외 사항 명확화"},
                {"title": "역할/책임(RACI) 배정", "pct": 0.20, "type": "decision", "purpose": "담당자 확정"},
                {"title": "일정/마일스톤 계획", "pct": 0.20, "type": "discussion", "purpose": "주요 기한 합의"},
                {"title": "리스크/질문 파킹랏", "pct": 0.10, "type": "info", "purpose": "우려사항 기록(Peak-End 긍정 마무리)"},
            ],
        },
    }

    # ── 메인 디스패처 ────────────────────────

    async def execute(self, **kwargs: Any) -> dict:
        action = kwargs.get("action", "full")
        actions = {
            "full": self._full,
            "sequence": self._sequence,
            "timeboxing": self._timeboxing,
            "energy": self._energy,
            "facilitate": self._facilitate,
            "template": self._template,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return {
            "status": "error",
            "message": (
                f"알 수 없는 action: {action}. "
                "sequence, timeboxing, energy, facilitate, template, full 중 하나를 사용하세요."
            ),
        }

    # ═══════════════════════════════════════════════════════
    #  1. sequence — 안건 최적 순서 배치
    # ═══════════════════════════════════════════════════════

    async def _sequence(self, params: dict) -> dict:
        """Allen(2015) + Peak-End Rule 기반 안건 최적 순서 결정.

        배치 원칙:
          ① 중요 의사결정 → 회의 초반 (인지 에너지 최고)
          ② 브레인스토밍 → 중반 (워밍업 후)
          ③ 정보 공유 → 후반 (에너지 낮아도 가능)
          ④ 긍정적/가벼운 아이템 → 마지막 (Peak-End Rule)
        """
        items = params.get("items", [])
        if not items:
            return {"status": "error", "message": "items 리스트가 필요합니다. [{title, type, complexity, energy_required, estimated_minutes}]"}

        # 각 아이템에 정렬 키 계산
        scored_items = []
        total_minutes = sum(it.get("estimated_minutes", 10) for it in items)
        for it in items:
            item_type = it.get("type", "discussion")
            complexity = it.get("complexity", 5)
            energy_req = it.get("energy_required", 5)

            # 정렬 점수: 타입 우선순위(낮을수록 앞) + 에너지 요구량(높을수록 앞)
            type_priority = self.TYPE_PRIORITY.get(item_type, 3)
            sort_score = type_priority * 10 - energy_req - complexity * 0.5

            scored_items.append({
                **it,
                "_sort_score": sort_score,
                "_type_priority": type_priority,
            })

        # 정렬: sort_score 오름차순 (낮을수록 앞배치)
        sorted_items = sorted(scored_items, key=lambda x: x["_sort_score"])

        # Peak-End Rule: 마지막 아이템이 info나 긍정적이면 그대로, 아니면 조정
        if len(sorted_items) >= 2:
            last = sorted_items[-1]
            # info 타입이 있으면 마지막으로 이동
            for i, it in enumerate(sorted_items[:-1]):
                if it.get("type") == "info" and it.get("energy_required", 5) <= 4:
                    sorted_items.append(sorted_items.pop(i))
                    break

        # 에너지 소모 시뮬레이션
        remaining_energy = 100.0
        sequence_with_energy = []
        elapsed = 0
        for it in sorted_items:
            item_type = it.get("type", "discussion")
            minutes = it.get("estimated_minutes", 10)
            complexity = it.get("complexity", 5)
            drain = self.TYPE_ENERGY_DRAIN.get(item_type, 1.0)
            energy_cost = (minutes / total_minutes) * 50 * drain + complexity * 1.5

            sequence_with_energy.append({
                "title": it.get("title", "무제"),
                "type": item_type,
                "estimated_minutes": minutes,
                "complexity": complexity,
                "energy_at_start": round(remaining_energy, 1),
                "energy_cost": round(energy_cost, 1),
                "timing": f"{elapsed}~{elapsed + minutes}분",
            })
            remaining_energy = max(0, remaining_energy - energy_cost)
            elapsed += minutes

        # LLM 해석
        items_str = "\n".join(
            f"  {i+1}. {it['title']} (유형: {it['type']}, 복잡도: {it.get('complexity', '?')}, 에너지: {it['energy_at_start']}%)"
            for i, it in enumerate(sequence_with_energy)
        )
        prompt = (
            "회의 안건 최적 배치 결과를 분석하세요.\n"
            f"총 소요 시간: {total_minutes}분, 안건 수: {len(items)}개\n"
            f"배치 순서:\n{items_str}\n\n"
            "배치 이유, 주의점, 에너지 관리 팁을 간결하게 설명하세요."
        )
        llm_result = await self._llm_call(prompt, "안건 순서 최적화 분석 요청")

        return {
            "status": "success",
            "action": "sequence",
            "result": {
                "optimized_sequence": sequence_with_energy,
                "total_minutes": total_minutes,
                "final_energy": round(remaining_energy, 1),
                "principles_applied": [
                    "Allen(2015): 의사결정 → 초반 배치",
                    "Peak-End Rule: 가벼운 안건 → 마무리",
                    "에너지 곡선: 고에너지 안건 우선",
                ],
            },
            "llm_interpretation": llm_result,
        }

    # ═══════════════════════════════════════════════════════
    #  2. timeboxing — 시간 배분 최적화
    # ═══════════════════════════════════════════════════════

    async def _timeboxing(self, params: dict) -> dict:
        """Parkinson's Law 보정 기반 시간 배분."""
        items = params.get("items", [])
        total_minutes = int(params.get("total_minutes", 60))
        if not items:
            return {"status": "error", "message": "items 리스트와 total_minutes가 필요합니다."}

        # Parkinson 보정: 사람들은 20~30% 과대추정 (연구 기반)
        parkinson_factor = 0.7

        raw_total = sum(it.get("estimated_minutes", 10) for it in items)
        corrected_items = []
        for it in items:
            est = it.get("estimated_minutes", 10)
            corrected = max(5, round(est * parkinson_factor))  # 최소 5분 보장
            corrected_items.append({
                "title": it.get("title", "무제"),
                "original_minutes": est,
                "corrected_minutes": corrected,
                "savings": est - corrected,
            })

        corrected_total = sum(ci["corrected_minutes"] for ci in corrected_items)

        # 여유시간(buffer) 확보: 전체의 10%
        buffer_minutes = max(3, round(total_minutes * 0.1))
        available = total_minutes - buffer_minutes

        # 비례 배분
        if corrected_total > available:
            ratio = available / max(corrected_total, 1)
            for ci in corrected_items:
                ci["allocated_minutes"] = max(5, round(ci["corrected_minutes"] * ratio))
        else:
            for ci in corrected_items:
                ci["allocated_minutes"] = ci["corrected_minutes"]

        allocated_total = sum(ci["allocated_minutes"] for ci in corrected_items)
        actual_buffer = total_minutes - allocated_total

        # 과적 경고
        overloaded = allocated_total > total_minutes * 0.9
        warning = None
        if overloaded:
            excess = allocated_total - round(total_minutes * 0.9)
            warning = f"안건이 과적됩니다! {excess}분 초과 — 안건을 {math.ceil(excess / 5)}개 줄이거나 회의 시간을 늘리세요."

        # LLM 해석
        prompt = (
            "Parkinson's Law 기반 시간 배분 결과를 분석하세요.\n"
            f"전체 시간: {total_minutes}분, 안건: {len(items)}개\n"
            f"원래 추정 합계: {raw_total}분 → 보정 후: {corrected_total}분 (Parkinson ×0.7)\n"
            f"{'⚠️ 과적 경고: ' + warning if warning else '시간 여유 있음'}\n\n"
            "시간 관리 팁과 각 안건별 조언을 간결하게 제시하세요."
        )
        llm_result = await self._llm_call(prompt, "시간 배분 최적화 분석 요청")

        return {
            "status": "success",
            "action": "timeboxing",
            "result": {
                "items": corrected_items,
                "total_minutes": total_minutes,
                "buffer_minutes": actual_buffer,
                "raw_total": raw_total,
                "corrected_total": corrected_total,
                "allocated_total": allocated_total,
                "parkinson_factor": parkinson_factor,
                "overloaded": overloaded,
                "warning": warning,
            },
            "llm_interpretation": llm_result,
        }

    # ═══════════════════════════════════════════════════════
    #  3. energy — 에너지 곡선 매핑
    # ═══════════════════════════════════════════════════════

    async def _energy(self, params: dict) -> dict:
        """일주기(Circadian) + 회의 내 피로도 + 참석자 수 보정 에너지 곡선."""
        start_time = params.get("start_time", "10:00")
        items = params.get("items", [])
        participant_count = int(params.get("participant_count", 6))

        if not items:
            return {"status": "error", "message": "start_time, items, participant_count가 필요합니다."}

        hour, minute = _parse_time(start_time)

        # Ringelmann 효과: 참석자 10명 초과 시 추가 인원당 -1%
        ringelmann_penalty = max(0, participant_count - 10) * 1.0

        total_minutes = sum(it.get("estimated_minutes", 10) for it in items)
        elapsed = 0
        energy_timeline = []

        for it in items:
            minutes = it.get("estimated_minutes", 10)
            cur_hour, cur_minute = _add_minutes(hour, minute, elapsed)
            time_str = _format_time(cur_hour, cur_minute)

            # ① 일주기 에너지 (시간대별, 보간)
            circadian = self._get_circadian_energy(cur_hour, cur_minute)

            # ② 회의 내 피로: 30분부터 5분마다 -2% (Rogelberg)
            meeting_fatigue = 0.0
            if elapsed > 30:
                meeting_fatigue = ((elapsed - 30) / 5) * 2.0

            # ③ Ringelmann 보정
            combined_energy = _clamp(
                circadian * 100 - meeting_fatigue - ringelmann_penalty, 0, 100
            )

            # 에너지 수준 평가
            if combined_energy >= 80:
                energy_label = "최상 — 의사결정·복잡한 토론에 적합"
            elif combined_energy >= 60:
                energy_label = "양호 — 일반 토론·브레인스토밍에 적합"
            elif combined_energy >= 40:
                energy_label = "보통 — 정보 공유·간단한 안건에 적합"
            else:
                energy_label = "저에너지 — 쉬는 시간 필요 또는 가벼운 안건만"

            item_type = it.get("type", "discussion")
            energy_required = it.get("energy_required", 5)
            mismatch = energy_required > 7 and combined_energy < 60

            energy_timeline.append({
                "title": it.get("title", "무제"),
                "time": time_str,
                "elapsed_minutes": elapsed,
                "energy_level": round(combined_energy, 1),
                "energy_label": energy_label,
                "circadian": round(circadian * 100, 1),
                "meeting_fatigue": round(meeting_fatigue, 1),
                "mismatch_warning": "이 안건은 높은 에너지가 필요하지만 현재 에너지가 낮습니다!" if mismatch else None,
            })
            elapsed += minutes

        # LLM 해석
        warnings = [t for t in energy_timeline if t["mismatch_warning"]]
        prompt = (
            "회의 에너지 곡선 분석 결과를 해석하세요.\n"
            f"시작: {start_time}, 참석자: {participant_count}명, 총 {total_minutes}분\n"
            f"{'⚠️ 에너지 부족 안건 ' + str(len(warnings)) + '개 발견' if warnings else '에너지 배분 양호'}\n\n"
            "에너지 관리 전략과 개선 제안을 제시하세요."
        )
        llm_result = await self._llm_call(prompt, "에너지 곡선 매핑 분석 요청")

        return {
            "status": "success",
            "action": "energy",
            "result": {
                "energy_timeline": energy_timeline,
                "parameters": {
                    "start_time": start_time,
                    "participant_count": participant_count,
                    "total_minutes": total_minutes,
                    "ringelmann_penalty": round(ringelmann_penalty, 1),
                },
                "mismatch_count": len(warnings),
            },
            "llm_interpretation": llm_result,
        }

    def _get_circadian_energy(self, hour: int, minute: int) -> float:
        """시간대별 에너지를 선형 보간으로 계산 (0~1)."""
        time_str = f"{hour:02d}:00"
        next_hour_str = f"{(hour + 1) % 24:02d}:00"

        current_e = self.CIRCADIAN_ENERGY.get(time_str, 0.6)
        next_e = self.CIRCADIAN_ENERGY.get(next_hour_str, current_e)

        fraction = minute / 60.0
        return current_e + (next_e - current_e) * fraction

    # ═══════════════════════════════════════════════════════
    #  4. facilitate — 퍼실리테이션 가이드 생성
    # ═══════════════════════════════════════════════════════

    async def _facilitate(self, params: dict) -> dict:
        """Schwarz(2017) 기반 안건별 퍼실리테이션 기법 추천 + 진행 스크립트."""
        items = params.get("items", [])
        if not items:
            return {"status": "error", "message": "items 리스트가 필요합니다. [{title, type, desired_outcome}]"}

        guides = []
        for it in items:
            item_type = it.get("type", "discussion")
            title = it.get("title", "무제")
            outcome = it.get("desired_outcome", "결론 도출")

            techniques = self.FACILITATION_TECHNIQUES.get(item_type, self.FACILITATION_TECHNIQUES["discussion"])

            guides.append({
                "title": title,
                "type": item_type,
                "desired_outcome": outcome,
                "recommended_techniques": techniques,
            })

        # LLM으로 진행 스크립트 생성
        items_str = "\n".join(
            f"  - {g['title']} (유형: {g['type']}, 목표: {g['desired_outcome']})"
            for g in guides
        )
        prompt_system = (
            "숙련된 퍼실리테이터로서 각 안건별 진행 스크립트를 작성하세요.\n"
            "각 안건마다:\n"
            "1) 오프닝 멘트 (30초 이내, 안건 소개 + 목표 명확화)\n"
            "2) 추천 기법의 구체적 진행 방법 (1~2문장)\n"
            "3) 전환 멘트 (다음 안건으로 넘어가는 자연스러운 연결)\n"
            "4) 마무리 멘트 (결론/액션 아이템 요약)\n\n"
            "실제 말할 수 있는 자연스러운 한국어 문장으로 작성하세요."
        )
        llm_result = await self._llm_call(prompt_system, f"안건 목록:\n{items_str}")

        return {
            "status": "success",
            "action": "facilitate",
            "result": {
                "facilitation_guides": guides,
                "principles": [
                    "Schwarz(2017): 과정에 집중, 내용은 참석자에게",
                    "모든 참석자의 동등한 발언 기회 보장",
                    "시각적 기록 (화이트보드/노트) 병행",
                ],
            },
            "llm_interpretation": llm_result,
        }

    # ═══════════════════════════════════════════════════════
    #  5. template — 아젠다 템플릿 생성
    # ═══════════════════════════════════════════════════════

    async def _template(self, params: dict) -> dict:
        """회의 유형별 연구 기반 최적 아젠다 템플릿."""
        meeting_type = params.get("meeting_type", "weekly_team")
        duration_minutes = int(params.get("duration_minutes", 60))

        template = self.MEETING_TEMPLATES.get(meeting_type)
        if not template:
            available = ", ".join(self.MEETING_TEMPLATES.keys())
            return {
                "status": "error",
                "message": f"알 수 없는 meeting_type: {meeting_type}. 사용 가능: {available}",
            }

        # 시간 배분 (비율 기반)
        agenda_items = []
        for section in template["sections"]:
            allocated = max(3, round(duration_minutes * section["pct"]))
            agenda_items.append({
                "title": section["title"],
                "allocated_minutes": allocated,
                "type": section["type"],
                "purpose": section["purpose"],
                "pct": round(section["pct"] * 100),
            })

        allocated_total = sum(ai["allocated_minutes"] for ai in agenda_items)

        # LLM으로 커스텀 조언
        prompt = (
            f"'{template['name_ko']}' ({duration_minutes}분) 아젠다 템플릿을 분석하세요.\n"
            f"섹션 수: {len(agenda_items)}개\n\n"
            "이 회의 유형에서 흔한 실수, 성공 팁, 준비 사항을 간결하게 조언하세요."
        )
        llm_result = await self._llm_call(prompt, f"회의 유형: {meeting_type}, 시간: {duration_minutes}분")

        return {
            "status": "success",
            "action": "template",
            "result": {
                "meeting_type": meeting_type,
                "meeting_name_ko": template["name_ko"],
                "duration_minutes": duration_minutes,
                "agenda_items": agenda_items,
                "allocated_total": allocated_total,
                "peak_end_note": "마지막 섹션은 긍정적 마무리를 위해 설계되었습니다 (Kahneman, Peak-End Rule)",
            },
            "llm_interpretation": llm_result,
        }

    # ═══════════════════════════════════════════════════════
    #  6. full — 종합 분석
    # ═══════════════════════════════════════════════════════

    async def _full(self, params: dict) -> dict:
        """5개 분석 모듈 종합 실행."""
        items = params.get("items", [])
        if not items:
            return {"status": "error", "message": "items 리스트가 필요합니다."}

        results = {}

        # sequence
        results["sequence"] = await self._sequence(params)

        # timeboxing
        results["timeboxing"] = await self._timeboxing(params)

        # energy
        results["energy"] = await self._energy({
            "start_time": params.get("start_time", "10:00"),
            "items": items,
            "participant_count": params.get("participant_count", 6),
        })

        # facilitate
        results["facilitate"] = await self._facilitate(params)

        # template (기본 유형)
        meeting_type = params.get("meeting_type", "weekly_team")
        total_minutes = int(params.get("total_minutes", 60))
        results["template"] = await self._template({
            "meeting_type": meeting_type,
            "duration_minutes": total_minutes,
        })

        # 종합 요약
        seq_energy = results.get("sequence", {}).get("result", {}).get("final_energy", "?")
        mismatch = results.get("energy", {}).get("result", {}).get("mismatch_count", 0)
        overloaded = results.get("timeboxing", {}).get("result", {}).get("overloaded", False)

        prompt = (
            "회의 아젠다 종합 분석 결과를 요약하세요.\n"
            f"안건 수: {len(items)}개\n"
            f"종료 시 잔여 에너지: {seq_energy}%\n"
            f"에너지 부족 안건: {mismatch}개\n"
            f"시간 과적 여부: {'예' if overloaded else '아니오'}\n\n"
            "핵심 인사이트 3가지와 즉시 적용 가능한 개선안 2가지를 제시하세요."
        )
        llm_summary = await self._llm_call(prompt, "아젠다 종합 분석 요청")

        return {
            "status": "success",
            "action": "full",
            "results": results,
            "llm_summary": llm_summary,
        }
