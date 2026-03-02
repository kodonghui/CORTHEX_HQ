"""
CORTHEX HQ - Configuration Loader

arm_server.py에서 분리된 설정/초기화 모듈.
환경변수 로딩, 설정 파일 관리, 에이전트 빌드를 담당합니다.
"""
import json
import logging
import os
import re
import sys
from datetime import timezone, timedelta
from pathlib import Path

# 같은 폴더(web/)에서 임포트
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from state import app_state
from db import load_setting, save_setting

# Python 출력 버퍼링 비활성화 (systemd에서 로그가 바로 보이도록)
os.environ["PYTHONUNBUFFERED"] = "1"

# 진단 정보 수집용 → app_state.diag 사용
_diag = app_state.diag
_diag.update({"env_file": "", "env_count": 0,
              "tg_import": False, "tg_import_error": "",
              "tg_token_found": False, "tg_started": False, "tg_error": ""})


# ── 로깅 ──

def _log(msg: str) -> None:
    """디버그 로그 출력 (stdout + stderr 양쪽에 flush)."""
    print(msg, flush=True)
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


logger = logging.getLogger("corthex.arm_server")


# ── 텍스트 유틸리티 ──

_RE_MD_HEADER = re.compile(r'^#{1,3}\s+(.+)', re.MULTILINE)
_RE_SENTENCE_END = re.compile(r'[.!?。]\s')

def _extract_title_summary(content: str) -> str:
    """AI 응답 content에서 작전일지 제목으로 쓸 1줄 요약을 추출한다.
    우선순위: ① 마크다운 헤더(#~###) ② 첫 문장(50자) ③ 앞 80자 잘라내기
    """
    if not content:
        return ""
    text = content.strip()
    # ① 마크다운 헤더 추출
    m = _RE_MD_HEADER.search(text)
    if m:
        title = m.group(1).strip().rstrip('#').strip()
        if len(title) > 80:
            title = title[:77] + "..."
        return title
    # ② 첫 문장 추출 (마침표/느낌표/물음표 기준)
    first_line = text.split('\n')[0].strip()
    if first_line:
        m2 = _RE_SENTENCE_END.search(first_line)
        if m2 and m2.end() <= 80:
            return first_line[:m2.end()].strip()
        if len(first_line) <= 80:
            return first_line
    # ③ 앞 80자 잘라내기
    return text[:77].rstrip() + "..." if len(text) > 80 else text


# ── 환경변수 로딩 ──

def _load_env_file() -> None:
    """환경변수 파일을 직접 읽어서 os.environ에 설정."""
    env_paths = [
        Path("/home/ubuntu/corthex.env"),        # 서버 배포 환경
        Path(__file__).parent.parent / ".env.local",  # 로컬 개발 환경
        Path(__file__).parent.parent / ".env",        # 로컬 폴백
    ]
    for env_path in env_paths:
        _log(f"[ENV] 확인: {env_path} (존재: {env_path.exists()})")
        if env_path.exists():
            try:
                loaded = 0
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip()
                        if key:
                            os.environ[key] = value
                            loaded += 1
                _diag["env_loaded"] = True
                _diag["env_file"] = str(env_path)
                _diag["env_count"] = loaded
                tg = os.getenv("TELEGRAM_BOT_TOKEN", "")
                _diag["tg_token_found"] = bool(tg)
                _log(f"[ENV] ✅ {loaded}개 로드: {env_path}")
                _log(f"[ENV] TG_TOKEN: {bool(tg)} (길이:{len(tg)})")
            except Exception as e:
                _log(f"[ENV] ❌ 실패: {e}")
            break


_load_env_file()

# 프로젝트 루트를 sys.path에 추가 (src/ 모듈 임포트용)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    import yaml
except ImportError:
    yaml = None  # PyYAML 미설치 시 graceful fallback


# ── 타임존 ──

KST = timezone(timedelta(hours=9))


# ── 디렉토리 상수 ──

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
CONFIG_DIR = Path(BASE_DIR).parent / "config"
DATA_DIR = Path(BASE_DIR).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
KNOWLEDGE_DIR = Path(BASE_DIR).parent / "knowledge"
ARCHIVE_DIR = Path(BASE_DIR).parent / "archive"


# ── 빌드 번호 ──

def get_build_number() -> str:
    """빌드 번호 반환.
    실제 빌드 번호는 GitHub Actions 배포 시 deploy.yml이 HTML에 직접 주입함.
    이 함수는 로컬 개발 환경(배포 전)에서만 사용되는 폴백 값을 반환."""
    return "dev"


# ── 설정 파일 로드 ──

def _load_config(name: str) -> dict:
    """설정 파일 로드. JSON을 먼저 시도하고, 없으면 YAML로 시도."""
    # 1순위: JSON 파일 (deploy.yml이 배포 시 YAML → JSON으로 변환해둠)
    json_path = CONFIG_DIR / f"{name}.json"
    if json_path.exists():
        try:
            raw = json.loads(json_path.read_text(encoding="utf-8"))
            logger.info("%s.json 로드 성공", name)
            return raw
        except Exception as e:
            logger.warning("%s.json 로드 실패: %s", name, e)

    # 2순위: YAML 파일 (PyYAML 필요)
    yaml_path = CONFIG_DIR / f"{name}.yaml"
    if yaml is not None and yaml_path.exists():
        try:
            raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            logger.info("%s.yaml 로드 성공", name)
            # 보험: YAML 읽은 후 JSON도 자동 생성 (다음 기동 시 1순위로 바로 로드)
            try:
                json_path.write_text(
                    json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                logger.info("%s.yaml → %s.json 자동 변환 완료", name, name)
            except Exception as e:
                logger.debug("YAML→JSON 변환 저장 실패: %s", e)
            return raw
        except Exception as e:
            logger.warning("%s.yaml 로드 실패: %s", name, e)

    logger.warning("%s 설정 파일 로드 실패 (빈 설정 사용)", name)
    return {}


def _load_agents() -> dict:
    """에이전트별 상세 정보(allowed_tools, capabilities 등)를 로드."""
    raw = _load_config("agents")
    lookup: dict[str, dict] = {}
    for a in raw.get("agents", []):
        lookup[a["agent_id"]] = a
    return lookup


def _load_tools() -> list[dict]:
    """도구 목록을 로드."""
    raw = _load_config("tools")
    return raw.get("tools", [])


# 서버 시작 시 1회 로드 (메모리 절약: 필요한 정보만 캐시)
_AGENTS_DETAIL: dict[str, dict] = _load_agents()
_TOOLS_LIST: list[dict] = _load_tools()


# ── 데이터 영속 (DB 기반) ──

def _load_data(name: str, default=None):
    """DB에서 설정 데이터 로드. DB에 없으면 기존 JSON 파일 확인 후 자동 마이그레이션."""
    # 1순위: SQLite DB
    db_val = load_setting(name)
    if db_val is not None:
        return db_val
    # 2순위: 기존 JSON 파일 (자동 마이그레이션)
    path = DATA_DIR / f"{name}.json"
    if path.exists():
        try:
            val = json.loads(path.read_text(encoding="utf-8"))
            save_setting(name, val)  # DB로 마이그레이션
            return val
        except Exception as e:
            logger.debug("JSON→DB 마이그레이션 실패 (%s): %s", name, e)
    return default if default is not None else {}


def _save_data(name: str, data) -> None:
    """DB에 설정 데이터 저장."""
    save_setting(name, data)


def _save_config_file(name: str, data: dict) -> None:
    """설정 변경을 DB에 저장. (재배포해도 유지됨)"""
    save_setting(f"config_{name}", data)


def _sync_agent_defaults_to_db():
    """agents.yaml의 신규 에이전트만 agent_overrides DB에 추가.
    이미 DB에 존재하는 에이전트는 건드리지 않음 (사용자가 수동 변경한 모델 유지)."""
    try:
        agents_config = _load_config("agents")
        if not agents_config:
            return
        agents_list = agents_config.get("agents", [])

        overrides = _load_data("agent_overrides", {})
        changed = False

        for agent_data in agents_list:
            agent_id = agent_data.get("agent_id")
            if not agent_id:
                continue
            model_name = agent_data.get("model_name") or agent_data.get("model")
            reasoning = agent_data.get("reasoning_effort") or agent_data.get("reasoning")
            if not model_name:
                continue
            # DB에 없는 신규 에이전트만 yaml 기본값 적용 (기존 값은 보존)
            if agent_id not in overrides:
                overrides[agent_id] = {"model_name": model_name}
                if reasoning:
                    overrides[agent_id]["reasoning_effort"] = reasoning
                changed = True

        if changed:
            _save_data("agent_overrides", overrides)
            logger.info("agent_overrides DB 동기화: 신규 에이전트 %d건 추가", changed)
    except Exception as e:
        logger.warning("agent_overrides 동기화 실패: %s", e)


# ── 모델 매핑 ──

# 모델별 기본 추론 레벨 자동 매핑 (최신 2026년 기준)
MODEL_REASONING_MAP: dict[str, str] = {
    "claude-haiku-4-5-20251001": "low",
    "claude-sonnet-4-6":       "medium",
    "claude-opus-4-6":         "high",
    "gemini-3.1-pro-preview":    "high",
    "gemini-2.5-pro":          "high",
    "gpt-5.2":                 "high",
    "gpt-5.2-pro":             "xhigh",
    "gpt-5":                   "high",
    "gpt-5-mini":              "medium",
    "o3":                      "high",
    "o4-mini":                 "medium",
}

# 모델별 최대 출력 토큰 한도 (공식 API 기준, 2026년 2월)
MODEL_MAX_TOKENS_MAP: dict[str, int] = {
    "claude-haiku-4-5-20251001": 64000,
    "claude-sonnet-4-6":         64000,
    "claude-opus-4-6":           64000,
    "gemini-3.1-pro-preview":      64000,
    "gemini-2.5-pro":            65536,
    "gpt-5.2":                   128000,
    "gpt-5.2-pro":               128000,
    "gpt-5":                     128000,
    "gpt-5-mini":                32768,
    "o3":                        100000,
    "o4-mini":                   65536,
}


# ── 에이전트 목록 (agents.yaml에서 동적 로드) ──

_AGENTS_FALLBACK = [
    {"agent_id": "chief_of_staff", "name_ko": "비서실장", "role": "manager", "division": "secretary", "status": "idle", "model_name": "claude-sonnet-4-6", "cli_owner": "ceo"},
    {"agent_id": "leet_strategist", "name_ko": "전략팀장", "role": "manager", "division": "leet_master.strategy", "status": "idle", "model_name": "claude-sonnet-4-6", "cli_owner": "ceo"},
    {"agent_id": "leet_legal", "name_ko": "법무팀장", "role": "manager", "division": "leet_master.legal", "status": "idle", "model_name": "claude-sonnet-4-6", "cli_owner": "ceo"},
    {"agent_id": "leet_marketer", "name_ko": "마케팅팀장", "role": "manager", "division": "leet_master.marketing", "status": "idle", "model_name": "claude-sonnet-4-6", "cli_owner": "ceo"},
    {"agent_id": "fin_analyst", "name_ko": "금융분석팀장", "role": "manager", "division": "finance.investment", "status": "idle", "model_name": "claude-opus-4-6", "cli_owner": "ceo"},
    {"agent_id": "leet_publisher", "name_ko": "콘텐츠팀장", "role": "manager", "division": "publishing", "status": "idle", "model_name": "claude-sonnet-4-6", "cli_owner": "ceo"},
]


def _build_agents_from_yaml() -> list[dict]:
    """agents.yaml(또는 agents.json)에서 AGENTS 리스트를 동적 생성.
    로드 실패 시 _AGENTS_FALLBACK 사용."""
    try:
        agents_detail = _load_agents()  # _AGENTS_DETAIL과 동일 소스
        if not agents_detail:
            _log("[AGENTS] agents.yaml 로드 결과 비어있음 — 폴백 사용")
            return list(_AGENTS_FALLBACK)
        result = []
        for aid, detail in agents_detail.items():
            entry = {
                "agent_id": aid,
                "name_ko": detail.get("name_ko", aid),
                "role": detail.get("role", "specialist"),
                "division": detail.get("division", ""),
                "org": detail.get("org", "leet_master"),  # v5: 본부 (common/leet_master/sketchvibe/saju)
                "cli_owner": detail.get("cli_owner", "ceo"),  # v5: CLI 계정 (ceo/sister)
                "superior_id": detail.get("superior_id", ""),
                "dormant": detail.get("dormant", False),
                "status": "idle",
                "model_name": detail.get("model_name", "claude-sonnet-4-6"),
            }
            if detail.get("telegram_code"):
                entry["telegram_code"] = detail["telegram_code"]
            result.append(entry)
        _log(f"[AGENTS] agents.yaml에서 {len(result)}명 로드 완료")
        return result
    except Exception as e:
        _log(f"[AGENTS] agents.yaml 로드 실패 ({e}) — 폴백 사용")
        return list(_AGENTS_FALLBACK)


AGENTS = _build_agents_from_yaml()


# ── 워크스페이스 프로파일 (v5.1 네이버 모델) ──

_workspace_profiles: dict | None = None


def load_workspace_profiles() -> dict:
    """config/workspaces.yaml 로드 — 서버 시작 시 1회, 메모리 캐싱."""
    global _workspace_profiles
    if _workspace_profiles is not None:
        return _workspace_profiles
    # _load_config는 JSON 우선 → YAML 폴백 (기존 패턴 재사용)
    raw = _load_config("workspaces")
    _workspace_profiles = raw.get("workspaces", {})
    _log(f"[WORKSPACE] {len(_workspace_profiles)}개 워크스페이스 프로파일 로드")
    return _workspace_profiles


def get_workspace_profile(role: str) -> dict | None:
    """role에 해당하는 워크스페이스 프로파일 반환. 없으면 None."""
    return load_workspace_profiles().get(role)
