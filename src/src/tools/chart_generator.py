"""차트 생성기 도구 — 데이터를 시각적 차트/그래프로 변환."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.chart_generator")

OUTPUT_DIR = os.path.join(os.getcwd(), "output", "charts")


def _get_matplotlib():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm
        # 한글 폰트 설정
        for font_name in ["NanumGothic", "Malgun Gothic", "AppleGothic", "DejaVu Sans"]:
            if any(font_name in f.name for f in fm.fontManager.ttflist):
                plt.rcParams["font.family"] = font_name
                break
        plt.rcParams["axes.unicode_minus"] = False
        return plt
    except ImportError:
        return None


def _get_plotly():
    try:
        import plotly.graph_objects as go
        return go
    except ImportError:
        return None


class ChartGeneratorTool(BaseTool):
    """데이터를 막대/꺾은선/원형/캔들차트 등으로 시각화하는 도구."""

    async def execute(self, **kwargs: Any) -> Any:
        # query만 있고 데이터가 없는 경우 (tools.yaml 파라미터 스키마 미정의 시 폴백)
        # query를 data JSON으로 파싱 시도, 실패 시 사용법 안내 반환
        query = kwargs.get("query", "")
        if query and not kwargs.get("data") and not kwargs.get("labels") and not kwargs.get("values"):
            try:
                import json as _json
                parsed = _json.loads(query)
                kwargs["data"] = parsed
            except Exception:
                return (
                    "차트를 생성하려면 데이터가 필요합니다.\n\n"
                    "올바른 사용법:\n"
                    "- action: bar/line/pie/scatter 중 선택\n"
                    "- labels: 'X축 항목1, X축 항목2, ...'\n"
                    "- values: '값1, 값2, ...'\n"
                    "- 또는 data: '{\"항목1\": 값1, \"항목2\": 값2}' (JSON 형태)\n\n"
                    "예시: action=bar, labels='1월,2월,3월', values='100,200,300', title='월별 매출'"
                )

        action = kwargs.get("action", "bar")
        if action == "bar":
            return await self._bar(kwargs)
        elif action == "line":
            return await self._line(kwargs)
        elif action == "pie":
            return await self._pie(kwargs)
        elif action == "scatter":
            return await self._scatter(kwargs)
        elif action == "candlestick":
            return await self._candlestick(kwargs)
        elif action == "dashboard":
            return await self._dashboard(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능한 action: bar(막대), line(꺾은선), pie(원형), "
                "scatter(산점도), candlestick(캔들차트), dashboard(대시보드)"
            )

    # ── 공통 헬퍼 ──

    @staticmethod
    def _ensure_output_dir() -> str:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        return OUTPUT_DIR

    @staticmethod
    def _gen_filename(chart_type: str, ext: str = "png") -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{chart_type}_{ts}.{ext}"

    @staticmethod
    def _parse_data(kwargs: dict) -> tuple[list, list, str | None]:
        """데이터 파싱. labels, values, error 반환."""
        labels = kwargs.get("labels", [])
        values = kwargs.get("values", [])
        data = kwargs.get("data")

        if data:
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError:
                    return [], [], "data가 올바른 JSON 형식이 아닙니다."

            if isinstance(data, dict):
                labels = list(data.keys())
                values = list(data.values())
            elif isinstance(data, list) and data and isinstance(data[0], dict):
                label_key = kwargs.get("label_key", "name")
                value_key = kwargs.get("value_key", "value")
                labels = [item.get(label_key, "") for item in data]
                values = [item.get(value_key, 0) for item in data]

        if isinstance(labels, str):
            labels = [l.strip() for l in labels.split(",")]
        if isinstance(values, str):
            values = [float(v.strip()) for v in values.split(",")]

        if not labels or not values:
            return [], [], "데이터가 필요합니다. data(dict/list) 또는 labels+values를 입력하세요."

        return labels, values, None

    async def _bar(self, kwargs: dict) -> str:
        """막대 그래프."""
        plt = _get_matplotlib()
        if plt is None:
            return "matplotlib 라이브러리가 설치되지 않았습니다. pip install matplotlib"

        labels, values, err = self._parse_data(kwargs)
        if err:
            return err

        title = kwargs.get("title", "막대 그래프")
        xlabel = kwargs.get("xlabel", "")
        ylabel = kwargs.get("ylabel", "")
        color = kwargs.get("color", "#4F46E5")

        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(labels, values, color=color, edgecolor="white")
        ax.set_title(title, fontsize=16, fontweight="bold", pad=15)
        if xlabel:
            ax.set_xlabel(xlabel)
        if ylabel:
            ax.set_ylabel(ylabel)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        # 값 표시
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2., bar.get_height(),
                    f"{val:,.0f}" if isinstance(val, (int, float)) else str(val),
                    ha="center", va="bottom", fontsize=9)

        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()

        out_dir = self._ensure_output_dir()
        filename = self._gen_filename("bar")
        filepath = os.path.join(out_dir, filename)
        fig.savefig(filepath, dpi=150, bbox_inches="tight")
        plt.close(fig)

        logger.info("막대 차트 생성: %s", filepath)
        return f"## 차트 생성 완료\n\n- 유형: 막대 그래프\n- 제목: {title}\n- 저장 경로: {filepath}"

    async def _line(self, kwargs: dict) -> str:
        """꺾은선 그래프."""
        plt = _get_matplotlib()
        if plt is None:
            return "matplotlib 라이브러리가 설치되지 않았습니다. pip install matplotlib"

        labels, values, err = self._parse_data(kwargs)
        if err:
            return err

        title = kwargs.get("title", "꺾은선 그래프")
        xlabel = kwargs.get("xlabel", "")
        ylabel = kwargs.get("ylabel", "")
        color = kwargs.get("color", "#4F46E5")

        # 다중 시리즈 지원
        series_data = kwargs.get("series")
        fig, ax = plt.subplots(figsize=(10, 6))

        if series_data:
            if isinstance(series_data, str):
                series_data = json.loads(series_data)
            colors = ["#4F46E5", "#EF4444", "#10B981", "#F59E0B", "#8B5CF6"]
            for i, (name, vals) in enumerate(series_data.items()):
                ax.plot(labels, vals, marker="o", label=name,
                        color=colors[i % len(colors)], linewidth=2)
            ax.legend()
        else:
            ax.plot(labels, values, marker="o", color=color, linewidth=2)

        ax.set_title(title, fontsize=16, fontweight="bold", pad=15)
        if xlabel:
            ax.set_xlabel(xlabel)
        if ylabel:
            ax.set_ylabel(ylabel)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="y", alpha=0.3)
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()

        out_dir = self._ensure_output_dir()
        filename = self._gen_filename("line")
        filepath = os.path.join(out_dir, filename)
        fig.savefig(filepath, dpi=150, bbox_inches="tight")
        plt.close(fig)

        logger.info("꺾은선 차트 생성: %s", filepath)
        return f"## 차트 생성 완료\n\n- 유형: 꺾은선 그래프\n- 제목: {title}\n- 저장 경로: {filepath}"

    async def _pie(self, kwargs: dict) -> str:
        """원형 그래프."""
        plt = _get_matplotlib()
        if plt is None:
            return "matplotlib 라이브러리가 설치되지 않았습니다. pip install matplotlib"

        labels, values, err = self._parse_data(kwargs)
        if err:
            return err

        title = kwargs.get("title", "원형 그래프")
        colors = ["#4F46E5", "#EF4444", "#10B981", "#F59E0B", "#8B5CF6",
                   "#EC4899", "#06B6D4", "#84CC16", "#F97316", "#6366F1"]

        fig, ax = plt.subplots(figsize=(8, 8))
        wedges, texts, autotexts = ax.pie(
            values, labels=labels, autopct="%1.1f%%",
            colors=colors[:len(values)], startangle=90,
            pctdistance=0.85, textprops={"fontsize": 10},
        )
        for autotext in autotexts:
            autotext.set_fontsize(9)
        ax.set_title(title, fontsize=16, fontweight="bold", pad=20)

        plt.tight_layout()

        out_dir = self._ensure_output_dir()
        filename = self._gen_filename("pie")
        filepath = os.path.join(out_dir, filename)
        fig.savefig(filepath, dpi=150, bbox_inches="tight")
        plt.close(fig)

        logger.info("원형 차트 생성: %s", filepath)
        return f"## 차트 생성 완료\n\n- 유형: 원형 그래프\n- 제목: {title}\n- 저장 경로: {filepath}"

    async def _scatter(self, kwargs: dict) -> str:
        """산점도."""
        plt = _get_matplotlib()
        if plt is None:
            return "matplotlib 라이브러리가 설치되지 않았습니다. pip install matplotlib"

        x_values = kwargs.get("x", [])
        y_values = kwargs.get("y", [])

        if isinstance(x_values, str):
            x_values = [float(v.strip()) for v in x_values.split(",")]
        if isinstance(y_values, str):
            y_values = [float(v.strip()) for v in y_values.split(",")]

        if not x_values or not y_values:
            return "x, y 데이터를 입력해주세요."

        title = kwargs.get("title", "산점도")
        xlabel = kwargs.get("xlabel", "X")
        ylabel = kwargs.get("ylabel", "Y")

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.scatter(x_values, y_values, color="#4F46E5", alpha=0.7, s=60, edgecolors="white")
        ax.set_title(title, fontsize=16, fontweight="bold", pad=15)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(alpha=0.3)
        plt.tight_layout()

        out_dir = self._ensure_output_dir()
        filename = self._gen_filename("scatter")
        filepath = os.path.join(out_dir, filename)
        fig.savefig(filepath, dpi=150, bbox_inches="tight")
        plt.close(fig)

        logger.info("산점도 생성: %s", filepath)
        return f"## 차트 생성 완료\n\n- 유형: 산점도\n- 제목: {title}\n- 저장 경로: {filepath}"

    async def _candlestick(self, kwargs: dict) -> str:
        """주식 캔들스틱 차트 (plotly)."""
        go = _get_plotly()
        if go is None:
            return "plotly 라이브러리가 설치되지 않았습니다. pip install plotly"

        data = kwargs.get("data")
        if not data:
            return "OHLCV 데이터(data)가 필요합니다. [{date, open, high, low, close}, ...]"

        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return "data가 올바른 JSON 형식이 아닙니다."

        title = kwargs.get("title", "캔들스틱 차트")
        dates = [d.get("date", "") for d in data]
        opens = [d.get("open", 0) for d in data]
        highs = [d.get("high", 0) for d in data]
        lows = [d.get("low", 0) for d in data]
        closes = [d.get("close", 0) for d in data]

        fig = go.Figure(data=[go.Candlestick(
            x=dates, open=opens, high=highs, low=lows, close=closes,
            increasing_line_color="#EF4444", decreasing_line_color="#3B82F6",
        )])
        fig.update_layout(
            title=title, xaxis_title="날짜", yaxis_title="가격",
            template="plotly_white", height=500,
        )

        out_dir = self._ensure_output_dir()
        filename = self._gen_filename("candlestick", "html")
        filepath = os.path.join(out_dir, filename)
        fig.write_html(filepath)

        logger.info("캔들차트 생성: %s", filepath)
        return f"## 차트 생성 완료\n\n- 유형: 캔들스틱 차트\n- 제목: {title}\n- 저장 경로: {filepath}\n- 형식: HTML (브라우저에서 열기)"

    async def _dashboard(self, kwargs: dict) -> str:
        """다중 차트 대시보드 (plotly HTML)."""
        go = _get_plotly()
        if go is None:
            return "plotly 라이브러리가 설치되지 않았습니다. pip install plotly"

        try:
            from plotly.subplots import make_subplots
        except ImportError:
            return "plotly 라이브러리가 설치되지 않았습니다. pip install plotly"

        charts = kwargs.get("charts", [])
        if isinstance(charts, str):
            charts = json.loads(charts)

        if not charts:
            return (
                "대시보드에 포함할 차트 목록(charts)을 입력해주세요.\n"
                "예: [{\"type\": \"bar\", \"title\": \"매출\", \"labels\": [...], \"values\": [...]}, ...]"
            )

        title = kwargs.get("title", "대시보드")
        rows = (len(charts) + 1) // 2
        cols = min(len(charts), 2)

        fig = make_subplots(rows=rows, cols=cols, subplot_titles=[c.get("title", "") for c in charts])

        for i, chart in enumerate(charts):
            r = i // 2 + 1
            c = i % 2 + 1
            chart_type = chart.get("type", "bar")
            labels = chart.get("labels", [])
            values = chart.get("values", [])

            if chart_type == "bar":
                fig.add_trace(go.Bar(x=labels, y=values, name=chart.get("title", "")), row=r, col=c)
            elif chart_type == "line":
                fig.add_trace(go.Scatter(x=labels, y=values, mode="lines+markers", name=chart.get("title", "")), row=r, col=c)
            elif chart_type == "pie":
                fig.add_trace(go.Pie(labels=labels, values=values, name=chart.get("title", "")), row=r, col=c)

        fig.update_layout(title_text=title, height=400 * rows, template="plotly_white")

        out_dir = self._ensure_output_dir()
        filename = self._gen_filename("dashboard", "html")
        filepath = os.path.join(out_dir, filename)
        fig.write_html(filepath)

        logger.info("대시보드 생성: %s (%d개 차트)", filepath, len(charts))
        return f"## 대시보드 생성 완료\n\n- 제목: {title}\n- 차트 수: {len(charts)}개\n- 저장 경로: {filepath}\n- 형식: HTML (브라우저에서 열기)"
