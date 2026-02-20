"""
이해관계자 매핑 도구 (Stakeholder Mapper) — 프로젝트 이해관계자를 분석하고 관리 전략을 수립합니다.

프로젝트의 이해관계자들을 체계적으로 분류·분석하여
"누구를 어떻게 관리해야 하는지"를 정량적·정성적으로 판단합니다.

학술 근거:
  - Mitchell, Agle & Wood (1997) "Toward a Theory of Stakeholder Identification and Salience"
    → 3차원 돌출성 모델: Power × Urgency × Legitimacy → 7가지 유형 분류
  - Freeman (1984) "Strategic Management: A Stakeholder Approach"
    → 이해관계자 이론 원전, 전략적 관리 프레임워크
  - Mendelow (1991) Power-Interest Grid
    → 2×2 매트릭스 (권력 × 관심도) 기반 관리 전략 분류
  - Gardner et al. (1986) Stakeholder Influence Strategies
    → 참여 전략 분류 및 전환 프레임워크
  - Bourne & Walker (2005) Stakeholder Circle
    → 중요도 시각화 및 커뮤니케이션 계획 수립

사용 방법:
  - action="salience"        : Mitchell 돌출성 분석 (3D: Power × Urgency × Legitimacy)
  - action="power_interest"  : Mendelow Power-Interest Grid (2×2 매트릭스)
  - action="influence"       : 영향력 네트워크 분석 (중심성 + 허브 식별)
  - action="engagement"      : 참여 수준 GAP 분석 (Gardner 기반)
  - action="strategy"        : 이해관계자별 맞춤 관리 전략 생성 (LLM)
  - action="full"            : 위 5개 종합 분석

필요 환경변수: 없음
필요 라이브러리: 없음 (순수 Python)
"""
from __future__ import annotations

import logging
import math
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.stakeholder_mapper")

# 타입 힌트 편의용
_ConnectionMap = dict[str, list[str]]


# ═══════════════════════════════════════════════════════
#  유틸리티 함수
# ═══════════════════════════════════════════════════════

def _mean(vals: list) -> float:
    """리스트의 평균을 반환합니다. 빈 리스트이면 0.0."""
    return sum(vals) / len(vals) if vals else 0.0


def _clamp(value: float, low: float = 1.0, high: float = 10.0) -> float:
    """값을 [low, high] 범위로 제한합니다."""
    return max(low, min(high, value))


# ═══════════════════════════════════════════════════════
#  상수 데이터
# ═══════════════════════════════════════════════════════

# Mitchell 7가지 돌출성 유형 (Power, Urgency, Legitimacy 조합)
SALIENCE_TYPES = {
    (True, True, True):    {"type": "Definitive",    "ko": "결정적",   "priority": 1,
                            "strategy": "최우선 관리 — 모든 의사결정에 참여시키고 즉각 대응"},
    (True, False, True):   {"type": "Dominant",      "ko": "지배적",   "priority": 2,
                            "strategy": "기대 충족 필수 — 정기 보고 및 기대사항 관리"},
    (True, True, False):   {"type": "Dangerous",     "ko": "위험",     "priority": 3,
                            "strategy": "위험 대비 — 즉시 대응 체계 구축, 갈등 예방"},
    (False, True, True):   {"type": "Dependent",     "ko": "의존적",   "priority": 4,
                            "strategy": "지원 제공 — 필요 자원 확보 및 대변인 역할"},
    (True, False, False):  {"type": "Dormant",       "ko": "잠재적",   "priority": 5,
                            "strategy": "모니터링 — 권력 활성화 시점 감시, 최소 접촉"},
    (False, False, True):  {"type": "Discretionary",  "ko": "재량적",   "priority": 6,
                            "strategy": "정보 제공 — 뉴스레터/보고서 등 일방향 소통"},
    (False, True, False):  {"type": "Demanding",     "ko": "요구적",   "priority": 7,
                            "strategy": "최소 관리 — 과도한 요구 시 경계 설정"},
}

# Mendelow Power-Interest Grid 4사분면
PI_QUADRANTS = {
    "manage_closely":  {"ko": "긴밀 관리", "range": "High Power + High Interest",
                        "strategy": "적극 참여 — 핵심 의사결정자로 대우, 1:1 커뮤니케이션, 빈번한 업데이트"},
    "keep_satisfied":  {"ko": "만족 유지", "range": "High Power + Low Interest",
                        "strategy": "만족 유지 — 관심을 자극하되 과부하 금지, 핵심만 간결히 보고"},
    "keep_informed":   {"ko": "정보 제공", "range": "Low Power + High Interest",
                        "strategy": "정보 제공 — 정기 뉴스레터, 의견 청취 채널 개방, 지지자로 육성"},
    "monitor":         {"ko": "모니터링",  "range": "Low Power + Low Interest",
                        "strategy": "최소 관리 — 대규모 공지만, 변화 시 재평가"},
}

# 참여 수준 (Gardner 기반) — 수치화 매핑
ENGAGEMENT_LEVELS = {
    "unaware":    {"score": 1, "ko": "미인지",  "desc": "프로젝트 존재 자체를 모름"},
    "resistant":  {"score": 2, "ko": "저항",    "desc": "프로젝트에 반대하거나 방해"},
    "neutral":    {"score": 3, "ko": "중립",    "desc": "관심 없음, 영향 없음"},
    "supportive": {"score": 4, "ko": "지지",    "desc": "프로젝트를 긍정적으로 지원"},
    "leading":    {"score": 5, "ko": "주도",    "desc": "적극적으로 추진하고 옹호"},
}

# GAP별 전환 전략 (from → to)
TRANSITION_STRATEGIES = {
    (-4, "저항→주도"):   "단계적 접근: 1:1 면담으로 우려 파악 → 소규모 성과 공유 → 역할 부여 → 리더십 위임",
    (-3, "저항→지지"):   "1:1 면담으로 우려사항 파악 → 반대 이유 해소 → 빠른 성과(Quick Win) 공유",
    (-2, "저항→중립"):   "1:1 면담으로 반대 이유 경청 → 직접적 영향 최소화 약속 → 정기 업데이트 제공",
    (-1, "미인지→저항"):  "비정상 상태 — 인식 전 저항 불가, 데이터 재확인 필요",
    (1, "미인지→저항"):   "비정상 상태 — 역방향 전환, 원인 분석 필요",
    (2, "미인지→중립"):   "프로젝트 소개 세션 + FAQ 문서 배포 + 질의응답 채널 개방",
    (3, "미인지→지지"):   "프로젝트 비전 발표 + 기대 혜택 구체적 제시 + 초기 참여 기회 제공",
    (4, "미인지→주도"):   "비전 공유 + 핵심 역할 제안 + 의사결정 참여 + 인센티브 설계",
    (1, "중립→지지"):     "빠른 성과(Quick Win) 공유 + 프로젝트 혜택 개인화 + 소규모 역할 부여",
    (2, "중립→주도"):     "성과 공유 + 핵심 역할 부여 + 의사결정 참여 + 공식 인정(표창)",
    (1, "지지→주도"):     "리더십 역할 공식 부여 + 의사결정 권한 위임 + 공개 인정 및 보상",
}

# 영향력 유형별 가중치
INFLUENCE_TYPE_WEIGHTS = {
    "formal":   1.0,   # 공식 권한 (직급, 계약)
    "informal": 0.8,   # 비공식 영향력 (인맥, 카리스마)
    "expert":   0.9,   # 전문성 기반 영향력
    "resource": 0.85,  # 자원 통제 기반 영향력
}


# ═══════════════════════════════════════════════════════
#  StakeholderMapperTool
# ═══════════════════════════════════════════════════════

class StakeholderMapperTool(BaseTool):
    """교수급 이해관계자 매핑 도구 — Mitchell 돌출성 + Mendelow Grid + 네트워크 + GAP 분석."""

    # ── 메인 디스패처 ────────────────────────

    async def execute(self, **kwargs: Any) -> dict:
        action = kwargs.get("action", "full")

        actions = {
            "full":           self._full_analysis,
            "salience":       self._salience_analysis,
            "power_interest": self._power_interest_grid,
            "influence":      self._influence_network,
            "engagement":     self._engagement_gap,
            "strategy":       self._strategy_generation,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)

        return {
            "status": "error",
            "message": (
                f"알 수 없는 action: {action}. "
                "salience, power_interest, influence, engagement, strategy, full 중 하나를 사용하세요."
            ),
        }

    # ═══════════════════════════════════════════════════
    #  1) Mitchell 돌출성 분석 (Power × Urgency × Legitimacy)
    # ═══════════════════════════════════════════════════

    async def _salience_analysis(self, params: dict) -> dict:
        """Mitchell et al. (1997) 3차원 돌출성 분석 — 7가지 유형으로 분류합니다."""
        stakeholders = params.get("stakeholders", [])
        if not stakeholders:
            return {"status": "error", "message": "stakeholders 리스트가 필요합니다. "
                    "형식: [{name, role, power(1-10), urgency(1-10), legitimacy(1-10)}]"}

        threshold = params.get("threshold", 5.0)  # 속성 보유 판단 기준
        results = []

        for sh in stakeholders:
            name = sh.get("name", "이름 없음")
            role = sh.get("role", "역할 미지정")
            p = _clamp(float(sh.get("power", 5)))
            u = _clamp(float(sh.get("urgency", 5)))
            l = _clamp(float(sh.get("legitimacy", 5)))

            # 속성 보유 여부 (threshold 초과 시 보유)
            has_p = p > threshold
            has_u = u > threshold
            has_l = l > threshold

            # 속성 개수로 돌출성 수준 결정
            attr_count = sum([has_p, has_u, has_l])

            # 7가지 유형 매칭
            key = (has_p, has_u, has_l)
            type_info = SALIENCE_TYPES.get(key, {
                "type": "Non-stakeholder", "ko": "비이해관계자", "priority": 8,
                "strategy": "현재 관리 불필요 — 상황 변화 시 재평가"
            })

            # Salience Score = (P + U + L) / 3
            salience_score = round((p + u + l) / 3, 2)

            results.append({
                "name": name,
                "role": role,
                "scores": {"power": p, "urgency": u, "legitimacy": l},
                "attributes": {"has_power": has_p, "has_urgency": has_u, "has_legitimacy": has_l,
                               "count": attr_count},
                "salience_score": salience_score,
                "salience_level": "높음" if attr_count == 3 else ("중간" if attr_count == 2
                                  else ("낮음" if attr_count == 1 else "없음")),
                "type": type_info["type"],
                "type_ko": type_info["ko"],
                "priority": type_info["priority"],
                "strategy": type_info["strategy"],
            })

        # 우선순위순 정렬
        results.sort(key=lambda x: (x["priority"], -x["salience_score"]))

        # 유형별 분포 통계
        type_distribution = {}
        for r in results:
            t = r["type_ko"]
            type_distribution[t] = type_distribution.get(t, 0) + 1

        summary = {
            "total_stakeholders": len(results),
            "type_distribution": type_distribution,
            "avg_salience_score": round(_mean([r["salience_score"] for r in results]), 2),
            "top_priority": results[0]["name"] if results else "없음",
        }

        # LLM 해석
        analysis_text = "\n".join(
            f"- {r['name']}({r['role']}): {r['type_ko']}({r['type']}), "
            f"점수={r['salience_score']}, P={r['scores']['power']}/U={r['scores']['urgency']}/L={r['scores']['legitimacy']}"
            for r in results
        )
        llm = await self._llm_call(
            "당신은 이해관계자 관리 전문 컨설턴트입니다. Mitchell(1997) 돌출성 이론에 기반하여 분석 결과를 해석하세요.",
            f"아래 Mitchell 돌출성 분석 결과를 해석하고, 우선 관리 대상과 주의사항을 한국어로 정리해주세요.\n\n"
            f"분석 결과:\n{analysis_text}\n\n유형 분포: {type_distribution}"
        )

        return {"status": "success", "analysis": "salience", "results": results,
                "summary": summary, "llm_interpretation": llm}

    # ═══════════════════════════════════════════════════
    #  2) Mendelow Power-Interest Grid
    # ═══════════════════════════════════════════════════

    async def _power_interest_grid(self, params: dict) -> dict:
        """Mendelow (1991) Power-Interest Grid — 4사분면으로 분류합니다."""
        stakeholders = params.get("stakeholders", [])
        if not stakeholders:
            return {"status": "error", "message": "stakeholders 리스트가 필요합니다. "
                    "형식: [{name, power(1-10), interest(1-10)}]"}

        threshold = params.get("threshold", 5.0)
        quadrants = {"manage_closely": [], "keep_satisfied": [], "keep_informed": [], "monitor": []}

        for sh in stakeholders:
            name = sh.get("name", "이름 없음")
            power = _clamp(float(sh.get("power", 5)))
            interest = _clamp(float(sh.get("interest", 5)))

            high_power = power > threshold
            high_interest = interest > threshold

            if high_power and high_interest:
                q_key = "manage_closely"
            elif high_power and not high_interest:
                q_key = "keep_satisfied"
            elif not high_power and high_interest:
                q_key = "keep_informed"
            else:
                q_key = "monitor"

            quadrants[q_key].append({
                "name": name,
                "power": power,
                "interest": interest,
                "quadrant": PI_QUADRANTS[q_key]["ko"],
                "strategy": PI_QUADRANTS[q_key]["strategy"],
            })

        # 사분면별 통계
        grid_summary = {}
        for q_key, members in quadrants.items():
            grid_summary[PI_QUADRANTS[q_key]["ko"]] = {
                "count": len(members),
                "members": [m["name"] for m in members],
                "strategy": PI_QUADRANTS[q_key]["strategy"],
            }

        llm = await self._llm_call(
            "당신은 프로젝트 관리 전문 컨설턴트입니다. Mendelow Power-Interest Grid 결과를 해석하세요.",
            f"아래 Power-Interest Grid 분류 결과를 해석하고, 사분면별 관리 전략을 한국어로 정리해주세요.\n\n"
            f"Grid 결과: {grid_summary}"
        )

        return {"status": "success", "analysis": "power_interest", "quadrants": quadrants,
                "grid_summary": grid_summary, "llm_interpretation": llm}

    # ═══════════════════════════════════════════════════
    #  3) 영향력 네트워크 분석
    # ═══════════════════════════════════════════════════

    async def _influence_network(self, params: dict) -> dict:
        """네트워크 중심성 기반 영향력 분석 — 핵심 허브를 식별합니다."""
        stakeholders = params.get("stakeholders", [])
        if not stakeholders:
            return {"status": "error", "message": "stakeholders 리스트가 필요합니다. "
                    "형식: [{name, connections(list), influence_type}]"}

        n = len(stakeholders)
        if n < 2:
            return {"status": "error", "message": "최소 2명의 이해관계자가 필요합니다."}

        name_set = {sh.get("name", "") for sh in stakeholders}

        # ── 1단계: 각 노드별 유효 연결 + 연결 맵 구축 ──
        node_connections: dict[str, list[str]] = {}  # 이름 → 유효 연결 리스트
        results = []

        for sh in stakeholders:
            name = sh.get("name", "이름 없음")
            connections = sh.get("connections", [])
            inf_type = sh.get("influence_type", "formal")
            type_weight = INFLUENCE_TYPE_WEIGHTS.get(inf_type, 0.7)

            # Degree centrality: 유효 연결 수 / (n-1)
            valid_connections = [c for c in connections if c in name_set and c != name]
            node_connections[name] = valid_connections
            degree_centrality = round(len(valid_connections) / (n - 1), 4) if n > 1 else 0.0

            results.append({
                "name": name,
                "influence_type": inf_type,
                "influence_type_weight": type_weight,
                "connections": valid_connections,
                "connection_count": len(valid_connections),
                "degree_centrality": degree_centrality,
                "type_weight": type_weight,
            })

        # ── 2단계: 매개 중심성 (Betweenness Centrality) 계산 ──
        # 간략화된 매개 중심성: 노드 k가 i와 j 사이의 "다리" 역할을 하는 횟수
        # 조건: k가 i, j 모두와 연결되어 있지만, i와 j는 직접 연결되지 않은 경우 → k에 +1
        all_names = list(node_connections.keys())
        betweenness_raw: dict[str, int] = {name: 0 for name in all_names}

        for i_idx in range(len(all_names)):
            for j_idx in range(i_idx + 1, len(all_names)):
                node_i = all_names[i_idx]
                node_j = all_names[j_idx]
                # i와 j가 직접 연결되어 있는지 확인
                i_conns = set(node_connections.get(node_i, []))
                j_conns = set(node_connections.get(node_j, []))
                directly_connected = node_j in i_conns or node_i in j_conns

                if not directly_connected:
                    # i와 j 모두에 연결된 노드 k를 찾으면 → k가 다리 역할
                    for k_name in all_names:
                        if k_name == node_i or k_name == node_j:
                            continue
                        k_conns = set(node_connections.get(k_name, []))
                        # k가 i, j 모두와 연결 (양방향 중 하나라도)
                        k_to_i = node_i in k_conns or k_name in i_conns
                        k_to_j = node_j in k_conns or k_name in j_conns
                        if k_to_i and k_to_j:
                            betweenness_raw[k_name] += 1

        # 정규화: 최대 가능 쌍 수 = (n-1)(n-2)/2
        max_pairs = (n - 1) * (n - 2) / 2 if n > 2 else 1.0
        betweenness_normalized: dict[str, float] = {
            name: round(count / max_pairs, 4) for name, count in betweenness_raw.items()
        }

        # ── 3단계: 가중 중심성 = degree 50% + betweenness 30% + type_weight 20% ──
        for r in results:
            name = r["name"]
            r["betweenness_raw"] = betweenness_raw.get(name, 0)
            r["betweenness_centrality"] = betweenness_normalized.get(name, 0.0)
            r["weighted_centrality"] = round(
                r["degree_centrality"] * 0.5
                + r["betweenness_centrality"] * 0.3
                + r["type_weight"] * 0.2,
                4,
            )
            # 브릿지 노드 판별: 매개 중심성 높고 연결도 중간 (상위 50% 이하)
            # (정렬 후 최종 판별)

        # 중심성 기준 정렬
        results.sort(key=lambda x: -x["weighted_centrality"])

        # ── 4단계: 브릿지 노드 식별 ──
        # 브릿지 = 매개 중심성이 중앙값 이상 + 연결도가 중앙값 이하 → 핵심 연결자
        degree_values = sorted([r["degree_centrality"] for r in results])
        between_values = sorted([r["betweenness_centrality"] for r in results])
        degree_median = degree_values[len(degree_values) // 2] if degree_values else 0
        between_median = between_values[len(between_values) // 2] if between_values else 0

        bridge_nodes = []
        for r in results:
            is_bridge = (
                r["betweenness_centrality"] > between_median
                and r["degree_centrality"] <= degree_median
                and r["betweenness_raw"] > 0
            )
            r["is_bridge"] = is_bridge
            if is_bridge:
                bridge_nodes.append(r["name"])

        # 상위 20% = 핵심 허브
        hub_threshold = max(1, math.ceil(n * 0.2))
        for i, r in enumerate(results):
            r["is_hub"] = i < hub_threshold

        hubs = [r["name"] for r in results if r["is_hub"]]
        non_hubs = [r["name"] for r in results if not r["is_hub"]]

        # 간접 영향 경로 추천: 비허브 → 허브 → 타겟
        influence_paths = []
        for nh in non_hubs:
            nh_data = next((r for r in results if r["name"] == nh), None)
            if not nh_data:
                continue
            # 비허브가 연결된 허브를 찾아서 경로 추천
            connected_hubs = [c for c in nh_data["connections"] if c in hubs]
            if connected_hubs:
                influence_paths.append({
                    "target": nh,
                    "via_hubs": connected_hubs,
                    "recommendation": f"'{connected_hubs[0]}'을(를) 통한 간접 영향 전략 추천",
                })

        network_summary = {
            "total_nodes": n,
            "hubs": hubs,
            "bridge_nodes": bridge_nodes,
            "hub_ratio": round(len(hubs) / n * 100, 1),
            "avg_degree_centrality": round(_mean([r["degree_centrality"] for r in results]), 4),
            "avg_betweenness_centrality": round(_mean([r["betweenness_centrality"] for r in results]), 4),
            "avg_weighted_centrality": round(_mean([r["weighted_centrality"] for r in results]), 4),
            "max_centrality": results[0]["weighted_centrality"] if results else 0.0,
            "centrality_formula": "degree×0.5 + betweenness×0.3 + type_weight×0.2",
            "influence_paths_count": len(influence_paths),
        }

        llm = await self._llm_call(
            "당신은 조직 네트워크 분석(ONA) 전문가입니다. 영향력 네트워크 결과를 해석하세요.",
            f"아래 이해관계자 네트워크 분석 결과를 해석하고, 핵심 허브 및 브릿지 노드 활용 전략을 한국어로 정리해주세요.\n\n"
            f"허브 (높은 가중 중심성): {hubs}\n"
            f"브릿지 노드 (높은 매개 중심성, 중간 연결도 — 핵심 연결자): {bridge_nodes}\n"
            f"비허브: {non_hubs}\n간접 영향 경로: {influence_paths}\n"
            f"네트워크 요약: {network_summary}\n\n"
            f"브릿지 노드를 잃으면 네트워크가 분절되므로, 이들의 관리가 특히 중요합니다."
        )

        return {"status": "success", "analysis": "influence", "results": results,
                "bridge_nodes": bridge_nodes,
                "influence_paths": influence_paths, "network_summary": network_summary,
                "llm_interpretation": llm}

    # ═══════════════════════════════════════════════════
    #  4) 참여 수준 GAP 분석 (Gardner 기반)
    # ═══════════════════════════════════════════════════

    async def _engagement_gap(self, params: dict) -> dict:
        """Gardner et al. (1986) 기반 참여 수준 GAP 분석 — 전환 전략을 제시합니다."""
        stakeholders = params.get("stakeholders", [])
        if not stakeholders:
            return {"status": "error", "message": "stakeholders 리스트가 필요합니다. "
                    "형식: [{name, current_engagement, desired_engagement}]"}

        results = []
        valid_levels = set(ENGAGEMENT_LEVELS.keys())

        for sh in stakeholders:
            name = sh.get("name", "이름 없음")
            current = sh.get("current_engagement", "neutral")
            desired = sh.get("desired_engagement", "supportive")

            if current not in valid_levels:
                current = "neutral"
            if desired not in valid_levels:
                desired = "supportive"

            current_score = ENGAGEMENT_LEVELS[current]["score"]
            desired_score = ENGAGEMENT_LEVELS[desired]["score"]
            gap = desired_score - current_score

            # 전환 전략 매칭
            transition_key = f"{ENGAGEMENT_LEVELS[current]['ko']}→{ENGAGEMENT_LEVELS[desired]['ko']}"
            strategy = TRANSITION_STRATEGIES.get(
                (gap, transition_key),
                TRANSITION_STRATEGIES.get(
                    (abs(gap), transition_key),
                    f"GAP {gap:+d}: 단계적 참여 수준 향상 전략 필요"
                )
            )

            # 전환 난이도 (GAP 크기 기반)
            abs_gap = abs(gap)
            difficulty = ("쉬움" if abs_gap <= 1 else ("보통" if abs_gap <= 2
                          else ("어려움" if abs_gap <= 3 else "매우 어려움")))

            # 예상 소요 기간 (경험적 추정)
            estimated_weeks = max(1, abs_gap * 3)  # GAP 1당 약 3주

            results.append({
                "name": name,
                "current": {"level": current, "ko": ENGAGEMENT_LEVELS[current]["ko"],
                            "score": current_score, "desc": ENGAGEMENT_LEVELS[current]["desc"]},
                "desired": {"level": desired, "ko": ENGAGEMENT_LEVELS[desired]["ko"],
                            "score": desired_score, "desc": ENGAGEMENT_LEVELS[desired]["desc"]},
                "gap": gap,
                "gap_direction": "향상 필요" if gap > 0 else ("유지" if gap == 0 else "역방향 (비정상)"),
                "difficulty": difficulty,
                "estimated_weeks": estimated_weeks,
                "transition_strategy": strategy,
            })

        # GAP 절대값 큰 순으로 우선순위 정렬
        results.sort(key=lambda x: (-abs(x["gap"]), x["name"]))

        gap_summary = {
            "total_stakeholders": len(results),
            "avg_gap": round(_mean([r["gap"] for r in results]), 2),
            "max_gap": max([abs(r["gap"]) for r in results], default=0),
            "critical_count": len([r for r in results if abs(r["gap"]) >= 3]),
            "on_target_count": len([r for r in results if r["gap"] == 0]),
        }

        llm = await self._llm_call(
            "당신은 변화관리(Change Management) 전문 컨설턴트입니다. "
            "참여 수준 GAP 분석 결과를 해석하세요.",
            f"아래 이해관계자 참여 수준 GAP 분석 결과를 해석하고, "
            f"우선순위별 전환 전략을 한국어로 정리해주세요.\n\n"
            f"분석 결과:\n" + "\n".join(
                f"- {r['name']}: {r['current']['ko']}→{r['desired']['ko']} "
                f"(GAP={r['gap']:+d}, 난이도={r['difficulty']})"
                for r in results
            ) + f"\n\nGAP 요약: {gap_summary}"
        )

        return {"status": "success", "analysis": "engagement", "results": results,
                "gap_summary": gap_summary, "llm_interpretation": llm}

    # ═══════════════════════════════════════════════════
    #  5) 맞춤 관리 전략 생성 (LLM 종합)
    # ═══════════════════════════════════════════════════

    async def _strategy_generation(self, params: dict) -> dict:
        """이해관계자별 맞춤 커뮤니케이션 및 관리 전략을 LLM으로 생성합니다."""
        stakeholders = params.get("stakeholders", [])
        project_context = params.get("project_context", "프로젝트 정보 없음")

        if not stakeholders:
            return {"status": "error", "message": "stakeholders 리스트가 필요합니다."}

        # 입력 데이터에서 가용한 정보 수집
        profiles = []
        for sh in stakeholders:
            name = sh.get("name", "이름 없음")
            role = sh.get("role", "역할 미지정")
            power = sh.get("power", 5)
            interest = sh.get("interest", 5)
            urgency = sh.get("urgency", 5)
            legitimacy = sh.get("legitimacy", 5)
            current_eng = sh.get("current_engagement", "neutral")
            desired_eng = sh.get("desired_engagement", "supportive")

            profiles.append(
                f"이름: {name}, 역할: {role}, "
                f"Power={power}, Interest={interest}, Urgency={urgency}, Legitimacy={legitimacy}, "
                f"현재참여={current_eng}, 목표참여={desired_eng}"
            )

        profiles_text = "\n".join(f"  {i+1}. {p}" for i, p in enumerate(profiles))

        llm = await self._llm_call(
            "당신은 이해관계자 관리 전략 수립 전문 컨설턴트입니다.\n"
            "Mitchell(1997) 돌출성 이론, Mendelow(1991) Grid, Gardner(1986) 참여 전략을 통합하여\n"
            "각 이해관계자에 대한 맞춤형 관리 전략을 수립합니다.\n"
            "반드시 한국어로 작성하세요.",
            f"프로젝트 맥락: {project_context}\n\n"
            f"이해관계자 프로필:\n{profiles_text}\n\n"
            f"각 이해관계자에 대해 다음을 포함한 맞춤 전략을 작성해주세요:\n"
            f"1. 커뮤니케이션 빈도 (매일/주간/격주/월간)\n"
            f"2. 선호 채널 (1:1 미팅, 이메일, 보고서, 전체 회의 등)\n"
            f"3. 메시지 프레임 (어떤 관점으로 소통할지)\n"
            f"4. 핵심 관리 포인트 (주의사항)\n"
            f"5. 단기 실행 항목 (즉시 할 일 1~2개)"
        )

        return {"status": "success", "analysis": "strategy",
                "stakeholder_count": len(stakeholders),
                "project_context": project_context,
                "llm_strategy": llm}

    # ═══════════════════════════════════════════════════
    #  6) 종합 분석 (Full)
    # ═══════════════════════════════════════════════════

    async def _full_analysis(self, params: dict) -> dict:
        """5가지 분석을 모두 수행하고 종합 보고서를 생성합니다."""
        stakeholders = params.get("stakeholders", [])
        if not stakeholders:
            return {"status": "error", "message": "stakeholders 리스트가 필요합니다."}

        results = {}

        # 가용 필드 확인 후 각 분석 실행
        analysis_actions = ["salience", "power_interest", "influence", "engagement", "strategy"]
        for act in analysis_actions:
            try:
                results[act] = await getattr(self, f"_{act.replace('power_interest', 'power_interest_grid').replace('influence', 'influence_network').replace('engagement', 'engagement_gap').replace('strategy', 'strategy_generation')}")(
                    {**params, "action": act}
                )
            except Exception as e:
                logger.warning("Full analysis — %s 분석 실패: %s", act, e)
                results[act] = {"status": "skipped", "reason": str(e)}

        # 종합 요약 LLM
        summary_parts = []
        for act, res in results.items():
            if res.get("status") == "success":
                llm_text = res.get("llm_interpretation") or res.get("llm_strategy", "")
                if llm_text:
                    summary_parts.append(f"[{act}] {llm_text[:300]}")

        llm = await self._llm_call(
            "당신은 프로젝트 관리 및 이해관계자 전략 수석 컨설턴트입니다.\n"
            "5가지 분석 결과를 종합하여 경영진 브리핑용 요약을 작성하세요.\n"
            "한국어로, 구조적으로 정리해주세요.",
            f"프로젝트: {params.get('project_context', '프로젝트 정보 없음')}\n"
            f"이해관계자 수: {len(stakeholders)}명\n\n"
            f"각 분석 핵심 결과:\n" + "\n\n".join(summary_parts) + "\n\n"
            f"위 결과를 종합하여 다음을 작성해주세요:\n"
            f"1. 핵심 발견사항 (3~5개)\n"
            f"2. 즉시 실행 항목 (우선순위순)\n"
            f"3. 리스크 요인 및 대응 방안\n"
            f"4. 주간 관리 계획 (로드맵)"
        )

        return {"status": "success", "analysis": "full",
                "results": results, "llm_summary": llm}
