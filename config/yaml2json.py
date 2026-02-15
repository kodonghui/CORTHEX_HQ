"""YAML → JSON 변환 스크립트.
deploy.yml에서 배포 시 실행하여 agents.yaml, tools.yaml을 JSON으로 변환.
mini_server.py가 PyYAML 없이도 설정 파일을 읽을 수 있도록 하기 위함.
"""
import json
import pathlib

try:
    import yaml
except ImportError:
    print("⚠️ PyYAML 미설치 — JSON 변환 건너뜀")
    exit(1)

config_dir = pathlib.Path("/home/ubuntu/config")

for name in ["agents", "tools"]:
    src = config_dir / f"{name}.yaml"
    dst = config_dir / f"{name}.json"
    if src.exists():
        data = yaml.safe_load(src.read_text(encoding="utf-8"))
        dst.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ✅ {name}.yaml → {name}.json 변환 완료")
    else:
        print(f"  ⚠️ {name}.yaml 없음")
