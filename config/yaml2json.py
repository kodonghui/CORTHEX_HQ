"""YAML → JSON 변환 스크립트.
deploy.yml에서 배포 시 실행하여 agents.yaml, tools.yaml을 JSON으로 변환.
arm_server.py가 PyYAML 없이도 설정 파일을 읽을 수 있도록 하기 위함.

사용법: python3 yaml2json.py [config_dir1] [config_dir2] ...
인자 없이 실행하면 기본 경로 2곳 모두 변환.
"""
import json
import pathlib
import sys

try:
    import yaml
except ImportError:
    print("⚠️ PyYAML 미설치 — JSON 변환 건너뜀")
    exit(1)

# 기본 경로: git 저장소 config + 복사된 config (둘 다 변환)
DEFAULT_DIRS = [
    "/home/ubuntu/CORTHEX_HQ/config",
    "/home/ubuntu/config",
]

config_dirs = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_DIRS

for config_dir_str in config_dirs:
    config_dir = pathlib.Path(config_dir_str)
    if not config_dir.exists():
        print(f"  ⚠️ {config_dir_str} 폴더 없음 — 건너뜀")
        continue

    for name in ["agents", "tools", "quality_rules"]:
        src = config_dir / f"{name}.yaml"
        dst = config_dir / f"{name}.json"
        if src.exists():
            data = yaml.safe_load(src.read_text(encoding="utf-8"))
            dst.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  ✅ {config_dir_str}/{name}.json 생성 완료")
        else:
            print(f"  ⚠️ {config_dir_str}/{name}.yaml 없음")
