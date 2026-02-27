"""
마케팅 채널 기여도 분석 도구 — 각 마케팅 채널이 매출에 얼마나 기여했는지 정밀 측정합니다.

"네이버 광고, 인스타, 유튜브 중에 뭐가 진짜 매출을 만들었나?"를 수학적으로 분석합니다.
기존의 단순 라스트클릭(마지막 터치만 인정) 방식이 아니라,
여러 채널이 협력한 효과까지 공정하게 배분합니다.

학술 근거:
  - Shapley Value (Shapley, 1953) — 게임이론 기반 공정 기여도 배분
  - Markov Chain Attribution (Anderl et al., 2016) — 전환 경로 확률 모델
  - Last-Touch / First-Touch / Linear / Time-Decay 비교 (Dalessandro et al., 2012)
  - Multi-Touch Attribution (Shao & Li, 2011)
  - Removal Effect (제거 효과) — 각 채널 제거 시 전환율 변화

사용 방법:
  - action="shapley"     : Shapley Value 기반 공정 기여도 배분
  - action="markov"      : Markov Chain 전환 확률 분석
  - action="compare"     : 6가지 기여 모델 비교 (Last/First/Linear/TimeDecay/Position/Shapley)
  - action="roi"         : 채널별 ROI + 예산 재배분 추천
  - action="path"        : 전환 경로 분석 (인기 경로, 평균 터치 포인트)
  - action="full"        : 종합 분석

필요 환경변수: 없음
필요 라이브러리: 없음 (순수 Python)
"""
from __future__ import annotations

import logging
import math
from itertools import combinations
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.marketing_attribution")


class MarketingAttributionTool(BaseTool):
    """교수급 마케팅 채널 기여도 분석 도구 (Shapley Value + Markov Chain)."""

    # ─── 기본 채널별 업계 평균 비용 (원/건) ───
    DEFAULT_CHANNEL_COSTS = {
        "search": 1500,    # 검색 광고
        "social": 800,     # SNS 광고
        "email": 200,      # 이메일
        "display": 1200,   # 디스플레이
        "referral": 500,   # 추천
        "organic": 0,      # 자연 유입
        "direct": 0,       # 직접 방문
        "affiliate": 2000, # 제휴
        "video": 2500,     # 영상 광고
        "blog": 300,       # 블로그/콘텐츠
    }

    async def execute(self, **kwargs) -> dict[str, Any]:
        action = kwargs.get("action", "full")
        dispatch = {
            "shapley": self._shapley_attribution,
            "markov": self._markov_attribution,
            "compare": self._compare_models,
            "roi": self._roi_analysis,
            "path": self._path_analysis,
            "full": self._full_analysis,
        }
        handler = dispatch.get(action)
        if not handler:
            return {"error": f"지원하지 않는 action: {action}. "
                    f"가능한 값: {list(dispatch.keys())}"}
        return await handler(**kwargs)

    # ═══════════════════════════════════════════════════════
    #  공통: 전환 경로 데이터 파싱
    # ═══════════════════════════════════════════════════════

    def _parse_paths(self, kwargs: dict) -> list[dict]:
        """전환 경로 데이터를 파싱합니다.

        paths_json: '[{"path":["search","social","direct"],"converted":true,"value":50000}, ...]'
        또는 기본 예시 데이터 사용
        """
        import json

        paths_raw = kwargs.get("paths_json", "")
        if paths_raw:
            try:
                return json.loads(paths_raw)
            except (json.JSONDecodeError, TypeError):
                pass

        # 기본 예시 데이터 (실무에서 흔한 패턴)
        return [
            {"path": ["search", "social", "direct"], "converted": True, "value": 50000},
            {"path": ["social", "email", "direct"], "converted": True, "value": 35000},
            {"path": ["display", "search", "direct"], "converted": True, "value": 42000},
            {"path": ["search", "direct"], "converted": True, "value": 28000},
            {"path": ["social", "direct"], "converted": True, "value": 22000},
            {"path": ["email", "direct"], "converted": True, "value": 18000},
            {"path": ["search"], "converted": True, "value": 15000},
            {"path": ["social"], "converted": True, "value": 12000},
            {"path": ["display", "social", "search", "direct"], "converted": True, "value": 65000},
            {"path": ["referral", "direct"], "converted": True, "value": 40000},
            {"path": ["blog", "search", "direct"], "converted": True, "value": 38000},
            {"path": ["video", "social", "direct"], "converted": True, "value": 55000},
            {"path": ["search", "display"], "converted": False, "value": 0},
            {"path": ["social"], "converted": False, "value": 0},
            {"path": ["display"], "converted": False, "value": 0},
            {"path": ["social", "display"], "converted": False, "value": 0},
            {"path": ["search"], "converted": False, "value": 0},
            {"path": ["email"], "converted": False, "value": 0},
            {"path": ["display", "search"], "converted": False, "value": 0},
            {"path": ["blog"], "converted": False, "value": 0},
        ]

    def _get_channels(self, paths: list[dict]) -> list[str]:
        """경로 데이터에서 고유 채널 목록을 추출합니다."""
        channels = set()
        for p in paths:
            for ch in p.get("path", []):
                channels.add(ch)
        return sorted(channels)

    # ═══════════════════════════════════════════════════════
    #  1. Shapley Value 기여도 (Shapley, 1953)
    # ═══════════════════════════════════════════════════════

    async def _shapley_attribution(self, **kwargs) -> dict[str, Any]:
        """Shapley Value: 게임이론 기반 공정 기여도 배분.

        각 채널의 기여도 = "그 채널이 있을 때와 없을 때 전환율 차이"를
        모든 가능한 채널 조합에서 평균낸 값.

        수학적 공식:
        φ_i = Σ_{S⊆N\\{i}} [|S|!(|N|-|S|-1)!/|N|!] × [v(S∪{i}) - v(S)]
        """
        paths = self._parse_paths(kwargs)
        channels = self._get_channels(paths)
        n = len(channels)

        if n > 10:
            # 채널 10개 초과 시 근사 계산 (정확한 Shapley는 2^n 복잡도)
            return await self._approximate_shapley(paths, channels, kwargs)

        # 특성 함수 v(S): 채널 집합 S에서의 전환 가치
        def coalition_value(channel_set: frozenset) -> float:
            total = 0.0
            for p in paths:
                if p.get("converted") and channel_set.issuperset(set(p["path"])):
                    total += p.get("value", 0)
            return total

        # Shapley Value 계산
        shapley_values = {}
        total_value = sum(p.get("value", 0) for p in paths if p.get("converted"))

        for i, channel in enumerate(channels):
            phi = 0.0
            others = [c for c in channels if c != channel]

            for size in range(n):
                for subset in combinations(others, size):
                    s_set = frozenset(subset)
                    s_with_i = frozenset(subset + (channel,))

                    marginal = coalition_value(s_with_i) - coalition_value(s_set)

                    # Shapley 가중치: |S|!(n-|S|-1)!/n!
                    weight = (math.factorial(size) * math.factorial(n - size - 1)
                              / math.factorial(n))
                    phi += weight * marginal

            shapley_values[channel] = phi

        # Removal Effect (제거 효과) 분석
        removal_effects = {}
        all_channels = frozenset(channels)
        baseline = coalition_value(all_channels)

        for channel in channels:
            without = all_channels - {channel}
            val_without = coalition_value(without)
            effect = baseline - val_without
            removal_effects[channel] = {
                "baseline_value": round(baseline),
                "value_without": round(val_without),
                "removal_effect": round(effect),
                "effect_pct": f"{(effect/baseline*100) if baseline > 0 else 0:.1f}%",
            }

        # 정규화 (전체 합이 total_value가 되도록)
        shapley_sum = sum(abs(v) for v in shapley_values.values())
        results = []
        for ch in sorted(shapley_values, key=shapley_values.get, reverse=True):
            raw = shapley_values[ch]
            normalized = (raw / shapley_sum * total_value) if shapley_sum > 0 else 0
            results.append({
                "channel": ch,
                "shapley_value": round(raw),
                "normalized_value": round(normalized),
                "contribution_pct": f"{(normalized/total_value*100) if total_value > 0 else 0:.1f}%",
                "rank": len(results) + 1,
            })

        return {
            "method": "Shapley Value (Shapley, 1953)",
            "description": "게임이론 기반 공정 기여도 — 각 채널의 한계 기여를 모든 조합에서 평균",
            "total_conversion_value": round(total_value),
            "channel_count": n,
            "attribution": results,
            "removal_effects": removal_effects,
            "interpretation": self._interpret_shapley(results),
        }

    async def _approximate_shapley(self, paths, channels, kwargs):
        """채널 10개 초과 시 몬테카를로 근사 Shapley."""
        import random
        n = len(channels)
        iterations = 5000
        marginals = {ch: 0.0 for ch in channels}

        def coalition_value(channel_set):
            total = 0.0
            for p in paths:
                if p.get("converted") and channel_set.issuperset(set(p["path"])):
                    total += p.get("value", 0)
            return total

        for _ in range(iterations):
            perm = channels[:]
            random.shuffle(perm)
            current_set = set()
            prev_val = 0.0
            for ch in perm:
                current_set.add(ch)
                new_val = coalition_value(frozenset(current_set))
                marginals[ch] += (new_val - prev_val)
                prev_val = new_val

        total_value = sum(p.get("value", 0) for p in paths if p.get("converted"))
        results = []
        for ch in sorted(marginals, key=marginals.get, reverse=True):
            avg = marginals[ch] / iterations
            results.append({
                "channel": ch,
                "shapley_value_approx": round(avg),
                "contribution_pct": f"{(avg/total_value*100) if total_value > 0 else 0:.1f}%",
            })

        return {
            "method": "Approximate Shapley (Monte Carlo, 5000 iterations)",
            "total_conversion_value": round(total_value),
            "attribution": results,
            "note": "채널 10개 초과로 근사 계산 적용",
        }

    def _interpret_shapley(self, results: list) -> str:
        if not results:
            return "분석 데이터 부족"
        top = results[0]
        return (f"가장 기여도 높은 채널: {top['channel']} "
                f"(전체의 {top['contribution_pct']}). "
                f"이 채널의 예산을 우선 확보하는 것이 권장됩니다.")

    # ═══════════════════════════════════════════════════════
    #  2. Markov Chain Attribution (Anderl et al., 2016)
    # ═══════════════════════════════════════════════════════

    async def _markov_attribution(self, **kwargs) -> dict[str, Any]:
        """Markov Chain: 전환 경로를 확률 전이 행렬로 모델링.

        각 채널 → 다음 채널로 이동 확률을 계산하고,
        특정 채널을 제거했을 때 전환율이 얼마나 떨어지는지로 기여도를 측정.
        """
        paths = self._parse_paths(kwargs)
        channels = self._get_channels(paths)

        # 상태: start → 각 채널 → conversion / null
        states = ["start"] + channels + ["conversion", "null"]

        # 전이 횟수 카운트
        transitions = {}
        for s1 in states:
            transitions[s1] = {}
            for s2 in states:
                transitions[s1][s2] = 0

        for p in paths:
            path = p.get("path", [])
            converted = p.get("converted", False)
            if not path:
                continue
            # start → 첫 채널
            transitions["start"][path[0]] += 1
            # 채널 → 채널
            for i in range(len(path) - 1):
                transitions[path[i]][path[i + 1]] += 1
            # 마지막 채널 → conversion/null
            if converted:
                transitions[path[-1]]["conversion"] += 1
            else:
                transitions[path[-1]]["null"] += 1

        # 전이 확률 행렬
        transition_probs = {}
        for s1 in states:
            total = sum(transitions[s1].values())
            transition_probs[s1] = {}
            for s2 in states:
                transition_probs[s1][s2] = transitions[s1][s2] / total if total > 0 else 0

        # 전체 전환율 계산 (시뮬레이션)
        base_conversion_rate = self._simulate_markov_conversion(
            transition_probs, states, channels
        )

        # 각 채널 제거 시 전환율 (Removal Effect)
        removal_effects = {}
        for remove_ch in channels:
            modified_probs = self._remove_channel(transition_probs, states, remove_ch)
            new_rate = self._simulate_markov_conversion(
                modified_probs, states, [c for c in channels if c != remove_ch]
            )
            effect = base_conversion_rate - new_rate
            removal_effects[remove_ch] = {
                "base_rate": f"{base_conversion_rate*100:.2f}%",
                "rate_without": f"{new_rate*100:.2f}%",
                "removal_effect": f"{effect*100:.2f}%p",
                "importance": round(effect / base_conversion_rate * 100, 1)
                              if base_conversion_rate > 0 else 0,
            }

        # 기여도 비율 (제거 효과 기준 정규화)
        total_effect = sum(
            base_conversion_rate - self._simulate_markov_conversion(
                self._remove_channel(transition_probs, states, ch),
                states, [c for c in channels if c != ch]
            )
            for ch in channels
        )

        attribution = []
        for ch in sorted(removal_effects, key=lambda x: removal_effects[x]["importance"],
                         reverse=True):
            eff = removal_effects[ch]
            raw_effect = base_conversion_rate - self._simulate_markov_conversion(
                self._remove_channel(transition_probs, states, ch),
                states, [c for c in channels if c != ch]
            )
            pct = (raw_effect / total_effect * 100) if total_effect > 0 else 0
            attribution.append({
                "channel": ch,
                "removal_importance": eff["importance"],
                "attribution_pct": f"{pct:.1f}%",
                **eff,
            })

        # 주요 전이 경로
        top_transitions = []
        for s1 in channels:
            for s2 in states:
                prob = transition_probs[s1][s2]
                if prob > 0.05 and s2 != s1:
                    top_transitions.append({
                        "from": s1, "to": s2,
                        "probability": f"{prob*100:.1f}%",
                    })
        top_transitions.sort(key=lambda x: float(x["probability"].rstrip("%")),
                             reverse=True)

        return {
            "method": "Markov Chain Attribution (Anderl et al., 2016)",
            "description": "전환 경로를 확률 전이 행렬로 모델링 → 채널 제거 시 전환율 변화로 기여도 측정",
            "base_conversion_rate": f"{base_conversion_rate*100:.2f}%",
            "channel_count": len(channels),
            "attribution": attribution,
            "top_transitions": top_transitions[:15],
        }

    def _simulate_markov_conversion(self, probs: dict, states: list,
                                     active_channels: list,
                                     max_steps: int = 20) -> float:
        """Markov Chain 시뮬레이션으로 전환율 계산 (행렬 거듭제곱)."""
        # start에서 시작하여 conversion에 도달할 확률
        current = {"start": 1.0}
        absorbed_conversion = 0.0
        absorbed_null = 0.0

        for _ in range(max_steps):
            next_state = {}
            for s, prob in current.items():
                if prob <= 1e-10 or s in ("conversion", "null"):
                    continue
                for s2 in states:
                    tp = probs.get(s, {}).get(s2, 0)
                    if tp > 0:
                        if s2 == "conversion":
                            absorbed_conversion += prob * tp
                        elif s2 == "null":
                            absorbed_null += prob * tp
                        else:
                            next_state[s2] = next_state.get(s2, 0) + prob * tp

            if not next_state:
                break
            current = next_state

        total = absorbed_conversion + absorbed_null
        return absorbed_conversion / total if total > 0 else 0

    def _remove_channel(self, probs: dict, states: list, channel: str) -> dict:
        """특정 채널을 제거한 전이 확률 행렬 생성."""
        new_probs = {}
        for s1 in states:
            new_probs[s1] = {}
            remaining_prob = 0.0
            for s2 in states:
                if s2 == channel:
                    continue
                new_probs[s1][s2] = probs.get(s1, {}).get(s2, 0)
                remaining_prob += new_probs[s1][s2]

            # 정규화 (제거된 채널로 가던 확률을 나머지에 분배)
            if remaining_prob > 0:
                for s2 in new_probs[s1]:
                    new_probs[s1][s2] /= remaining_prob
            new_probs[s1][channel] = 0

        return new_probs

    # ═══════════════════════════════════════════════════════
    #  3. 6가지 기여 모델 비교 (Dalessandro et al., 2012)
    # ═══════════════════════════════════════════════════════

    async def _compare_models(self, **kwargs) -> dict[str, Any]:
        """6가지 Attribution 모델을 동시에 비교합니다."""
        paths = self._parse_paths(kwargs)
        converted_paths = [p for p in paths if p.get("converted")]
        channels = self._get_channels(paths)

        models = {
            "last_touch": {},    # 마지막 터치만 인정
            "first_touch": {},   # 첫 터치만 인정
            "linear": {},        # 균등 배분
            "time_decay": {},    # 시간 가중 (최근일수록 높음)
            "position": {},      # U자형 (처음+마지막 40%, 나머지 20%)
            "shapley": {},       # Shapley Value
        }

        # 초기화
        for model in models:
            for ch in channels:
                models[model][ch] = 0.0

        total_value = sum(p.get("value", 0) for p in converted_paths)

        for p in converted_paths:
            path = p.get("path", [])
            value = p.get("value", 0)
            if not path:
                continue
            n = len(path)

            # Last Touch
            models["last_touch"][path[-1]] = models["last_touch"].get(path[-1], 0) + value

            # First Touch
            models["first_touch"][path[0]] = models["first_touch"].get(path[0], 0) + value

            # Linear
            share = value / n
            for ch in path:
                models["linear"][ch] = models["linear"].get(ch, 0) + share

            # Time Decay (반감기 = 7일, 각 터치포인트를 1일 간격으로 가정)
            decay_factor = 0.5  # 하루당 감쇠율
            weights = [decay_factor ** (n - 1 - i) for i in range(n)]
            weight_sum = sum(weights)
            for i, ch in enumerate(path):
                models["time_decay"][ch] = (
                    models["time_decay"].get(ch, 0) + value * weights[i] / weight_sum
                )

            # Position-Based (U-Shape)
            if n == 1:
                models["position"][path[0]] = models["position"].get(path[0], 0) + value
            elif n == 2:
                models["position"][path[0]] = models["position"].get(path[0], 0) + value * 0.5
                models["position"][path[1]] = models["position"].get(path[1], 0) + value * 0.5
            else:
                first_last_share = value * 0.4
                middle_total = value * 0.2
                middle_each = middle_total / (n - 2)
                models["position"][path[0]] = (
                    models["position"].get(path[0], 0) + first_last_share
                )
                models["position"][path[-1]] = (
                    models["position"].get(path[-1], 0) + first_last_share
                )
                for ch in path[1:-1]:
                    models["position"][ch] = models["position"].get(ch, 0) + middle_each

        # Shapley (이미 구현된 메서드 호출)
        shapley_result = await self._shapley_attribution(**kwargs)
        for item in shapley_result.get("attribution", []):
            ch = item["channel"]
            models["shapley"][ch] = item.get("normalized_value", 0)

        # 비교 테이블
        comparison = []
        for ch in channels:
            row = {"channel": ch}
            for model_name, values in models.items():
                val = values.get(ch, 0)
                row[model_name] = round(val)
                row[f"{model_name}_pct"] = (
                    f"{(val/total_value*100):.1f}%" if total_value > 0 else "0%"
                )
            comparison.append(row)

        # 모델 간 차이가 큰 채널 (논란 채널)
        controversial = []
        for ch in channels:
            vals = [models[m].get(ch, 0) for m in models]
            if max(vals) > 0:
                cv = (max(vals) - min(vals)) / max(vals) * 100  # 변동률
                if cv > 30:
                    controversial.append({
                        "channel": ch,
                        "variation": f"{cv:.0f}%",
                        "max_model": max(models, key=lambda m: models[m].get(ch, 0)),
                        "min_model": min(models, key=lambda m: models[m].get(ch, 0)),
                        "recommendation": "Shapley 또는 Markov 기여도를 기준으로 사용 권장",
                    })

        model_descriptions = {
            "last_touch": "마지막 터치만 100% 인정 (가장 단순, 과대평가 위험)",
            "first_touch": "첫 터치만 100% 인정 (인지 채널 과대평가)",
            "linear": "모든 터치에 균등 배분 (공정하지만 차별화 부족)",
            "time_decay": "최근 터치일수록 높은 가중치 (전환 근접 채널 우대)",
            "position": "처음+마지막 각 40%, 중간 20% (U자형, Google 추천)",
            "shapley": "게임이론 기반 한계 기여도 (가장 공정, 계산 복잡)",
        }

        return {
            "method": "6-Model Attribution Comparison (Dalessandro et al., 2012)",
            "description": "6가지 기여 모델로 같은 데이터를 분석 → 모델별 차이와 권장 모델 제시",
            "total_conversion_value": round(total_value),
            "model_descriptions": model_descriptions,
            "comparison": sorted(comparison,
                                 key=lambda x: x.get("shapley", 0), reverse=True),
            "controversial_channels": controversial,
            "recommendation": "Shapley 값이 가장 공정한 배분이지만 계산량이 많습니다. "
                             "실무에서는 Position-Based를 기본으로, 중요한 의사결정에 Shapley를 사용하세요.",
        }

    # ═══════════════════════════════════════════════════════
    #  4. 채널별 ROI 분석 + 예산 재배분
    # ═══════════════════════════════════════════════════════

    async def _roi_analysis(self, **kwargs) -> dict[str, Any]:
        """채널별 ROI 분석 + 최적 예산 재배분 추천."""
        paths = self._parse_paths(kwargs)
        channels = self._get_channels(paths)

        # 채널별 비용 파싱
        import json
        costs_raw = kwargs.get("channel_costs", "")
        if costs_raw:
            try:
                channel_costs = json.loads(costs_raw)
            except (json.JSONDecodeError, TypeError):
                channel_costs = {}
        else:
            channel_costs = {}

        monthly_budget = kwargs.get("monthly_budget", 5000000)

        # Shapley 기반 기여도 가져오기
        shapley_result = await self._shapley_attribution(**kwargs)
        attribution = {item["channel"]: item.get("normalized_value", 0)
                       for item in shapley_result.get("attribution", [])}

        total_value = shapley_result.get("total_conversion_value", 0)

        # 채널별 터치 횟수
        touch_counts = {}
        for p in paths:
            for ch in p.get("path", []):
                touch_counts[ch] = touch_counts.get(ch, 0) + 1

        # ROI 계산
        roi_data = []
        for ch in channels:
            revenue = attribution.get(ch, 0)
            cost_per = channel_costs.get(ch, self.DEFAULT_CHANNEL_COSTS.get(ch, 1000))
            touches = touch_counts.get(ch, 1)
            total_cost = cost_per * touches
            roi = ((revenue - total_cost) / total_cost * 100) if total_cost > 0 else float("inf")
            roas = revenue / total_cost if total_cost > 0 else float("inf")

            roi_data.append({
                "channel": ch,
                "attributed_revenue": round(revenue),
                "total_cost": round(total_cost),
                "touches": touches,
                "cost_per_touch": round(cost_per),
                "roi_pct": f"{roi:.0f}%" if roi != float("inf") else "∞",
                "roas": f"{roas:.1f}x" if roas != float("inf") else "∞",
                "profitable": revenue > total_cost,
            })

        roi_data.sort(key=lambda x: x["attributed_revenue"], reverse=True)

        # 최적 예산 재배분 (기여도 비율 기반 + ROI 가중치)
        reallocation = []
        weight_sum = 0
        weights = {}
        for item in roi_data:
            ch = item["channel"]
            rev = item["attributed_revenue"]
            roi_val = float(item["roi_pct"].rstrip("%")) if item["roi_pct"] != "∞" else 500
            # 기여도 × ROI 보정 가중치
            w = rev * max(0, (100 + roi_val) / 200)  # ROI 높을수록 가중치 증가
            weights[ch] = w
            weight_sum += w

        for item in roi_data:
            ch = item["channel"]
            w = weights.get(ch, 0)
            budget_share = (w / weight_sum) if weight_sum > 0 else 0
            allocated = monthly_budget * budget_share
            current_cost = item["total_cost"]
            change = allocated - current_cost

            reallocation.append({
                "channel": ch,
                "current_spend": round(current_cost),
                "recommended_spend": round(allocated),
                "budget_pct": f"{budget_share*100:.1f}%",
                "change": f"{'+' if change >= 0 else ''}{round(change):,}원",
                "direction": "증액 ↑" if change > 0 else ("감액 ↓" if change < 0 else "유지 →"),
            })

        return {
            "method": "Channel ROI + Budget Reallocation (Shapley-weighted)",
            "description": "Shapley 기여도 × ROI 효율을 결합해 최적 예산 배분 추천",
            "monthly_budget": f"{monthly_budget:,}원",
            "total_conversion_value": round(total_value),
            "roi_by_channel": roi_data,
            "budget_reallocation": reallocation,
            "key_insight": self._roi_insight(roi_data),
        }

    def _roi_insight(self, roi_data: list) -> str:
        profitable = [d for d in roi_data if d["profitable"]]
        unprofitable = [d for d in roi_data if not d["profitable"]]
        msg = f"수익 채널 {len(profitable)}개, 비수익 채널 {len(unprofitable)}개."
        if unprofitable:
            worst = unprofitable[-1]
            msg += f" 가장 비효율 채널: {worst['channel']} (ROI {worst['roi_pct']}). 예산 재검토 권장."
        return msg

    # ═══════════════════════════════════════════════════════
    #  5. 전환 경로 분석 (Shao & Li, 2011)
    # ═══════════════════════════════════════════════════════

    async def _path_analysis(self, **kwargs) -> dict[str, Any]:
        """전환 경로 패턴 분석 — 인기 경로, 평균 터치포인트, 채널 역할 분류."""
        paths = self._parse_paths(kwargs)
        converted = [p for p in paths if p.get("converted")]
        not_converted = [p for p in paths if not p.get("converted")]

        # 경로 패턴 빈도
        path_freq = {}
        for p in converted:
            key = " → ".join(p["path"])
            if key not in path_freq:
                path_freq[key] = {"count": 0, "total_value": 0}
            path_freq[key]["count"] += 1
            path_freq[key]["total_value"] += p.get("value", 0)

        top_paths = sorted(path_freq.items(), key=lambda x: x[1]["total_value"],
                           reverse=True)[:10]

        # 터치포인트 통계
        touch_lengths = [len(p["path"]) for p in converted]
        avg_touches = sum(touch_lengths) / len(touch_lengths) if touch_lengths else 0
        max_touches = max(touch_lengths) if touch_lengths else 0
        min_touches = min(touch_lengths) if touch_lengths else 0

        # 채널 역할 분류 (Introducer / Influencer / Closer)
        channel_roles = {}
        channels = self._get_channels(paths)
        for ch in channels:
            channel_roles[ch] = {"introducer": 0, "influencer": 0, "closer": 0, "solo": 0}

        for p in converted:
            path = p["path"]
            n = len(path)
            if n == 1:
                channel_roles[path[0]]["solo"] += 1
            else:
                channel_roles[path[0]]["introducer"] += 1
                channel_roles[path[-1]]["closer"] += 1
                for ch in path[1:-1]:
                    channel_roles[ch]["influencer"] += 1

        # 주요 역할 판정
        role_summary = []
        for ch in channels:
            roles = channel_roles[ch]
            total = sum(roles.values())
            if total == 0:
                continue
            primary_role = max(roles, key=roles.get)
            role_labels = {
                "introducer": "시작 채널 (인지)",
                "influencer": "중간 채널 (고려)",
                "closer": "전환 채널 (구매)",
                "solo": "단독 전환 채널",
            }
            role_summary.append({
                "channel": ch,
                "primary_role": role_labels[primary_role],
                "introducer_pct": f"{roles['introducer']/total*100:.0f}%",
                "influencer_pct": f"{roles['influencer']/total*100:.0f}%",
                "closer_pct": f"{roles['closer']/total*100:.0f}%",
                "solo_pct": f"{roles['solo']/total*100:.0f}%",
                "total_appearances": total,
            })

        # 전환 vs 비전환 경로 비교
        conv_lengths = [len(p["path"]) for p in converted]
        nonconv_lengths = [len(p["path"]) for p in not_converted]

        return {
            "method": "Conversion Path Analysis (Shao & Li, 2011)",
            "description": "전환 성공 경로의 패턴, 채널 역할(시작/중간/전환), 터치포인트 통계 분석",
            "conversion_stats": {
                "total_paths": len(paths),
                "converted": len(converted),
                "not_converted": len(not_converted),
                "conversion_rate": f"{len(converted)/len(paths)*100:.1f}%"
                                   if paths else "0%",
            },
            "touchpoint_stats": {
                "avg_touches": round(avg_touches, 1),
                "min_touches": min_touches,
                "max_touches": max_touches,
                "converted_avg": round(sum(conv_lengths)/len(conv_lengths), 1) if conv_lengths else 0,
                "non_converted_avg": round(sum(nonconv_lengths)/len(nonconv_lengths), 1) if nonconv_lengths else 0,
            },
            "top_converting_paths": [
                {"path": k, "conversions": v["count"],
                 "total_value": round(v["total_value"])}
                for k, v in top_paths
            ],
            "channel_roles": sorted(role_summary,
                                    key=lambda x: x["total_appearances"], reverse=True),
        }

    # ═══════════════════════════════════════════════════════
    #  6. 종합 분석
    # ═══════════════════════════════════════════════════════

    async def _full_analysis(self, **kwargs) -> dict[str, Any]:
        """전체 채널 기여도 종합 분석."""
        shapley = await self._shapley_attribution(**kwargs)
        markov = await self._markov_attribution(**kwargs)
        compare = await self._compare_models(**kwargs)
        roi = await self._roi_analysis(**kwargs)
        path = await self._path_analysis(**kwargs)

        # 종합 요약을 위해 LLM 호출
        summary_prompt = f"""아래 마케팅 채널 기여도 분석 결과를 한국어로 요약하세요.

## Shapley Value 기여도
{self._format_attribution(shapley.get('attribution', []))}

## Markov Chain 기여도
{self._format_attribution(markov.get('attribution', []))}

## 채널별 ROI
{self._format_roi(roi.get('roi_by_channel', []))}

## 전환 경로
- 평균 터치포인트: {path.get('touchpoint_stats', {}).get('avg_touches', 'N/A')}회
- 전환율: {path.get('conversion_stats', {}).get('conversion_rate', 'N/A')}

다음을 포함해서 작성:
1. 가장 효과적인 채널 2~3개와 이유
2. 예산 줄여야 할 채널과 이유
3. 구체적인 예산 재배분 추천
4. 채널 간 시너지 효과 분석"""

        summary = await self._llm_call(
            system_prompt="마케팅 채널 기여도 분석 전문가. 데이터 기반 구체적 추천.",
            user_prompt=summary_prompt,
        )

        return {
            "method": "Full Attribution Analysis",
            "shapley_attribution": shapley,
            "markov_attribution": markov,
            "model_comparison": compare,
            "roi_analysis": roi,
            "path_analysis": path,
            "executive_summary": summary,
        }

    def _format_attribution(self, items: list) -> str:
        lines = []
        for item in items[:5]:
            ch = item.get("channel", "?")
            pct = item.get("contribution_pct") or item.get("attribution_pct", "?")
            lines.append(f"- {ch}: {pct}")
        return "\n".join(lines) if lines else "데이터 없음"

    def _format_roi(self, items: list) -> str:
        lines = []
        for item in items[:5]:
            ch = item.get("channel", "?")
            roi = item.get("roi_pct", "?")
            roas = item.get("roas", "?")
            lines.append(f"- {ch}: ROI {roi}, ROAS {roas}")
        return "\n".join(lines) if lines else "데이터 없음"
