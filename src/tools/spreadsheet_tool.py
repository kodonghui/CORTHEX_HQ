"""스프레드시트 도구 — 엑셀/CSV 파일 읽기·쓰기·분석."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.spreadsheet_tool")


def _get_pandas():
    try:
        import pandas as pd
        return pd
    except ImportError:
        return None


def _get_openpyxl():
    try:
        import openpyxl
        return openpyxl
    except ImportError:
        return None


class SpreadsheetTool(BaseTool):
    """엑셀(xlsx)/CSV 파일 읽기·쓰기·분석·피벗 도구."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "read")
        if action == "read":
            return await self._read(kwargs)
        elif action == "write":
            return await self._write(kwargs)
        elif action == "analyze":
            return await self._analyze(kwargs)
        elif action == "filter":
            return await self._filter(kwargs)
        elif action == "pivot":
            return await self._pivot(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능한 action: read(읽기), write(쓰기), analyze(분석), "
                "filter(필터링), pivot(피벗 테이블)"
            )

    @staticmethod
    def _check_file(file_path: str) -> str | None:
        if not file_path:
            return "파일 경로(file_path)를 입력해주세요."
        if not os.path.isfile(file_path):
            return f"파일을 찾을 수 없습니다: {file_path}"
        ext = file_path.lower().rsplit(".", 1)[-1] if "." in file_path else ""
        if ext not in ("xlsx", "xls", "csv", "tsv"):
            return f"지원하지 않는 파일 형식입니다: .{ext} (xlsx, csv, tsv 지원)"
        return None

    def _read_dataframe(self, file_path: str, sheet_name: str | None = None):
        """파일을 pandas DataFrame으로 로드."""
        pd = _get_pandas()
        if pd is None:
            return None, "pandas 라이브러리가 설치되지 않았습니다. pip install pandas"

        ext = file_path.lower().rsplit(".", 1)[-1]
        try:
            if ext == "csv":
                df = pd.read_csv(file_path, encoding="utf-8-sig")
            elif ext == "tsv":
                df = pd.read_csv(file_path, sep="\t", encoding="utf-8-sig")
            else:
                sheet = sheet_name or 0
                df = pd.read_excel(file_path, sheet_name=sheet, engine="openpyxl")
            return df, None
        except Exception as e:
            return None, f"파일 읽기 실패: {e}"

    async def _read(self, kwargs: dict) -> str:
        """엑셀/CSV 파일 읽기."""
        file_path = kwargs.get("file_path", "")
        err = self._check_file(file_path)
        if err:
            return err

        sheet_name = kwargs.get("sheet_name")
        max_rows = int(kwargs.get("max_rows", 20))

        df, error = self._read_dataframe(file_path, sheet_name)
        if error:
            return error

        rows, cols = df.shape
        preview = df.head(max_rows).to_markdown(index=False)
        dtypes = "\n".join(f"  - {col}: {dtype}" for col, dtype in df.dtypes.items())

        return (
            f"## 스프레드시트 읽기 결과\n\n"
            f"- 파일: {file_path}\n"
            f"- 전체 행: {rows:,}행, 열: {cols}개\n"
            f"- 컬럼 타입:\n{dtypes}\n\n"
            f"### 미리보기 (상위 {min(max_rows, rows)}행)\n\n{preview}"
        )

    async def _write(self, kwargs: dict) -> str:
        """데이터를 엑셀/CSV로 저장."""
        pd = _get_pandas()
        if pd is None:
            return "pandas 라이브러리가 설치되지 않았습니다. pip install pandas"

        file_path = kwargs.get("file_path", "")
        data = kwargs.get("data")
        sheet_name = kwargs.get("sheet_name", "Sheet1")

        if not file_path:
            return "저장할 파일 경로(file_path)를 입력해주세요."
        if not data:
            return "저장할 데이터(data)를 입력해주세요. dict 리스트 또는 JSON 문자열"

        # JSON 문자열이면 파싱
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return "data가 올바른 JSON 형식이 아닙니다."

        try:
            df = pd.DataFrame(data)
        except Exception as e:
            return f"DataFrame 변환 실패: {e}"

        # 디렉토리 생성
        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        ext = file_path.lower().rsplit(".", 1)[-1] if "." in file_path else "xlsx"
        try:
            if ext == "csv":
                df.to_csv(file_path, index=False, encoding="utf-8-sig")
            elif ext == "tsv":
                df.to_csv(file_path, sep="\t", index=False, encoding="utf-8-sig")
            else:
                df.to_excel(file_path, index=False, sheet_name=sheet_name, engine="openpyxl")

            logger.info("파일 저장 완료: %s (%d행)", file_path, len(df))
            return (
                f"## 파일 저장 완료\n\n"
                f"- 경로: {file_path}\n"
                f"- 행: {len(df):,}행, 열: {len(df.columns)}개\n"
                f"- 컬럼: {', '.join(df.columns.tolist())}"
            )
        except Exception as e:
            return f"파일 저장 실패: {e}"

    async def _analyze(self, kwargs: dict) -> str:
        """파일 통계 분석."""
        file_path = kwargs.get("file_path", "")
        err = self._check_file(file_path)
        if err:
            return err

        df, error = self._read_dataframe(file_path, kwargs.get("sheet_name"))
        if error:
            return error

        pd = _get_pandas()
        desc = df.describe(include="all").to_markdown()
        null_info = "\n".join(
            f"  - {col}: {df[col].isnull().sum()}개 ({df[col].isnull().mean() * 100:.1f}%)"
            for col in df.columns if df[col].isnull().sum() > 0
        )

        stats_text = (
            f"## 데이터 분석 결과\n\n"
            f"- 파일: {file_path}\n"
            f"- 크기: {df.shape[0]:,}행 × {df.shape[1]}열\n\n"
            f"### 통계 요약\n\n{desc}\n\n"
        )
        if null_info:
            stats_text += f"### 결측값 현황\n\n{null_info}\n\n"

        # LLM 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 데이터 분석 전문가입니다. "
                "통계 요약을 보고 핵심 인사이트를 한국어로 설명하세요. "
                "비개발자도 이해할 수 있게 쉽게 설명하세요."
            ),
            user_prompt=stats_text,
        )

        return f"{stats_text}### 분석 인사이트\n\n{analysis}"

    async def _filter(self, kwargs: dict) -> str:
        """조건별 필터링."""
        file_path = kwargs.get("file_path", "")
        err = self._check_file(file_path)
        if err:
            return err

        column = kwargs.get("column", "")
        operator = kwargs.get("operator", "==")
        value = kwargs.get("value")

        if not column:
            return "필터링할 컬럼(column)을 입력해주세요."
        if value is None:
            return "필터링 값(value)을 입력해주세요."

        df, error = self._read_dataframe(file_path, kwargs.get("sheet_name"))
        if error:
            return error

        if column not in df.columns:
            return f"컬럼 '{column}'을 찾을 수 없습니다. 사용 가능한 컬럼: {', '.join(df.columns.tolist())}"

        try:
            if operator == "==":
                filtered = df[df[column] == value]
            elif operator == "!=":
                filtered = df[df[column] != value]
            elif operator == ">":
                filtered = df[df[column] > float(value)]
            elif operator == ">=":
                filtered = df[df[column] >= float(value)]
            elif operator == "<":
                filtered = df[df[column] < float(value)]
            elif operator == "<=":
                filtered = df[df[column] <= float(value)]
            elif operator == "contains":
                filtered = df[df[column].astype(str).str.contains(str(value), case=False, na=False)]
            else:
                return f"지원하지 않는 연산자: {operator}. 사용 가능: ==, !=, >, >=, <, <=, contains"
        except Exception as e:
            return f"필터링 실패: {e}"

        max_rows = int(kwargs.get("max_rows", 50))
        preview = filtered.head(max_rows).to_markdown(index=False)

        return (
            f"## 필터링 결과\n\n"
            f"- 조건: {column} {operator} {value}\n"
            f"- 결과: {len(filtered):,}행 (전체 {len(df):,}행 중)\n\n"
            f"{preview}"
        )

    async def _pivot(self, kwargs: dict) -> str:
        """피벗 테이블 생성."""
        file_path = kwargs.get("file_path", "")
        err = self._check_file(file_path)
        if err:
            return err

        index = kwargs.get("index", "")
        columns = kwargs.get("columns")
        values = kwargs.get("values", "")
        aggfunc = kwargs.get("aggfunc", "sum")

        if not index or not values:
            return "피벗 테이블에 필요한 인자: index(행), values(값). 선택: columns(열), aggfunc(집계함수: sum/mean/count)"

        df, error = self._read_dataframe(file_path, kwargs.get("sheet_name"))
        if error:
            return error

        pd = _get_pandas()
        try:
            pivot_kwargs = {"index": index, "values": values, "aggfunc": aggfunc}
            if columns:
                pivot_kwargs["columns"] = columns
            pivot_df = pd.pivot_table(df, **pivot_kwargs)
            preview = pivot_df.to_markdown()

            return (
                f"## 피벗 테이블 결과\n\n"
                f"- 행(index): {index}\n"
                f"- 값(values): {values}\n"
                f"- 집계: {aggfunc}\n"
                f"{'- 열(columns): ' + str(columns) if columns else ''}\n\n"
                f"{preview}"
            )
        except Exception as e:
            return f"피벗 테이블 생성 실패: {e}"
