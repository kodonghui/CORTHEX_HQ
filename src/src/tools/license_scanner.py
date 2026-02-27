"""
오픈소스 라이선스 분석 Tool.

오픈소스/소프트웨어 라이선스 의무·제한사항 분석 및 호환성 검사,
카피레프트(Copyleft) 전파 위험 진단.

사용 방법:
  - action="scan" (기본): 라이선스 이름 입력 → 의무·제한사항 상세 분석
  - action="check":       특정 사용 시나리오의 라이선스 준수 여부 확인
  - action="compatibility": 두 라이선스 간 호환성 검사
  - action="risk":          프로젝트 내 라이선스 조합의 종합 리스크 분석

필요 환경변수: 없음
의존 라이브러리: 없음 (순수 파이썬)

학술 기반:
  - Open Source Initiative (OSI) — 오픈소스 라이선스 인증 기준
  - Free Software Foundation (FSF) — GPL 호환성 매트릭스
  - SPDX License List (ISO/IEC 5962:2021) — 표준 라이선스 식별자
  - Copyleft Theory (Stallman, 1985) — 카피레프트 전파 개념
  - Van den Brande,";";"; Coughlan & Jaeger (2014)
    "The International Free and Open Source Software Law Book"
  - Wheeler (2014) "The Free-Libre / Open Source Software License Slide"
  - Rosen (2004) "Open Source Licensing: Software Freedom and IP Law"

주의: 이 분석은 참고용이며, 법적 확인은 반드시 전문 변호사에게 문의하세요.
"""
from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.license_scanner")

_DISCLAIMER = (
    "\n\n---\n**면책 안내**: 이 라이선스 분석은 참고용이며, "
    "법적 확인은 반드시 전문 변호사에게 문의하세요. "
    "(OSI, FSF, SPDX ISO/IEC 5962:2021 기반 분석)"
)

# ══════════════════════════════════════════
#  라이선스 카테고리 분류
# ══════════════════════════════════════════
#  FSF + OSI 분류 기반, Wheeler (2014) 슬라이드 참조

LICENSE_CATEGORIES: dict[str, str] = {
    # Permissive (허용적) — 거의 제한 없음
    "MIT": "permissive",
    "Apache-2.0": "permissive",
    "BSD-2-Clause": "permissive",
    "BSD-3-Clause": "permissive",
    "ISC": "permissive",
    "Zlib": "permissive",
    "Unlicense": "permissive",
    "0BSD": "permissive",
    "BSL-1.0": "permissive",
    # Weak Copyleft (약한 카피레프트) — 수정 부분만 공개
    "LGPL-2.1": "weak_copyleft",
    "LGPL-3.0": "weak_copyleft",
    "MPL-2.0": "weak_copyleft",
    "EPL-2.0": "weak_copyleft",
    "CDDL-1.0": "weak_copyleft",
    # Strong Copyleft (강한 카피레프트) — 전체 소스 공개 의무
    "GPL-2.0": "strong_copyleft",
    "GPL-3.0": "strong_copyleft",
    "AGPL-3.0": "strong_copyleft",
    "EUPL-1.2": "strong_copyleft",
    # Creative Commons (비소프트웨어)
    "CC-BY-4.0": "cc_permissive",
    "CC-BY-SA-4.0": "cc_copyleft",
    "CC-BY-NC-4.0": "cc_noncommercial",
    "CC-BY-NC-SA-4.0": "cc_nc_copyleft",
    "CC-BY-ND-4.0": "cc_noderivatives",
    "CC-BY-NC-ND-4.0": "cc_nc_nd",
    "CC0-1.0": "public_domain",
    # Proprietary (독점)
    "Proprietary": "proprietary",
}

# ══════════════════════════════════════════
#  라이선스 상세 데이터베이스
# ══════════════════════════════════════════
#  OSI Approved + FSF Free 기준, SPDX ID 사용

LICENSE_DB: dict[str, dict[str, Any]] = {
    "MIT": {
        "spdx_id": "MIT",
        "full_name": "MIT License",
        "category": "permissive",
        "osi_approved": True,
        "fsf_free": True,
        "copyleft": "없음",
        "commercial_use": True,
        "modification": True,
        "distribution": True,
        "private_use": True,
        "patent_grant": False,
        "obligations": [
            "저작권 고지 유지 (Copyright notice retention)",
            "라이선스 전문 포함 (License text inclusion)",
        ],
        "restrictions": [
            "보증 없음 — AS IS (No warranty)",
        ],
        "ai_training_safe": True,
        "summary_ko": (
            "가장 자유로운 라이선스. 거의 제한 없이 사용·수정·배포 가능. "
            "저작권 고지만 유지하면 됨."
        ),
    },
    "Apache-2.0": {
        "spdx_id": "Apache-2.0",
        "full_name": "Apache License 2.0",
        "category": "permissive",
        "osi_approved": True,
        "fsf_free": True,
        "copyleft": "없음",
        "commercial_use": True,
        "modification": True,
        "distribution": True,
        "private_use": True,
        "patent_grant": True,
        "obligations": [
            "저작권 고지 유지",
            "라이선스 전문 포함",
            "변경사항 표시 (NOTICE 파일)",
            "특허 라이선스 포함 (명시적 특허 허여)",
        ],
        "restrictions": [
            "상표권 미부여 — 원저작자 이름/상표 사용 불가",
            "보증 없음",
        ],
        "ai_training_safe": True,
        "summary_ko": (
            "MIT보다 약간 엄격하지만 여전히 자유로움. "
            "명시적 특허 허여가 장점. 변경사항 표시 의무."
        ),
    },
    "BSD-2-Clause": {
        "spdx_id": "BSD-2-Clause",
        "full_name": "BSD 2-Clause \"Simplified\" License",
        "category": "permissive",
        "osi_approved": True,
        "fsf_free": True,
        "copyleft": "없음",
        "commercial_use": True,
        "modification": True,
        "distribution": True,
        "private_use": True,
        "patent_grant": False,
        "obligations": [
            "저작권 고지 유지",
            "라이선스 전문 포함",
        ],
        "restrictions": [
            "보증 없음",
        ],
        "ai_training_safe": True,
        "summary_ko": "MIT와 거의 동일. 2가지 조건만 충족하면 자유롭게 사용 가능.",
    },
    "BSD-3-Clause": {
        "spdx_id": "BSD-3-Clause",
        "full_name": "BSD 3-Clause \"New\" or \"Revised\" License",
        "category": "permissive",
        "osi_approved": True,
        "fsf_free": True,
        "copyleft": "없음",
        "commercial_use": True,
        "modification": True,
        "distribution": True,
        "private_use": True,
        "patent_grant": False,
        "obligations": [
            "저작권 고지 유지",
            "라이선스 전문 포함",
        ],
        "restrictions": [
            "원저작자 이름을 보증/홍보에 사용 불가 (3번째 조항)",
            "보증 없음",
        ],
        "ai_training_safe": True,
        "summary_ko": "BSD-2에 '원저작자 이름 홍보 사용 금지' 조건 추가.",
    },
    "ISC": {
        "spdx_id": "ISC",
        "full_name": "ISC License",
        "category": "permissive",
        "osi_approved": True,
        "fsf_free": True,
        "copyleft": "없음",
        "commercial_use": True,
        "modification": True,
        "distribution": True,
        "private_use": True,
        "patent_grant": False,
        "obligations": ["저작권 고지 유지"],
        "restrictions": ["보증 없음"],
        "ai_training_safe": True,
        "summary_ko": "MIT의 간결한 버전. 실질적으로 MIT와 동일한 자유도.",
    },
    "LGPL-2.1": {
        "spdx_id": "LGPL-2.1-only",
        "full_name": "GNU Lesser General Public License v2.1",
        "category": "weak_copyleft",
        "osi_approved": True,
        "fsf_free": True,
        "copyleft": "약한 (라이브러리 수정분만)",
        "commercial_use": True,
        "modification": True,
        "distribution": True,
        "private_use": True,
        "patent_grant": False,
        "obligations": [
            "라이브러리 수정 시 소스코드 공개",
            "LGPL 라이브러리임을 고지",
            "사용자가 라이브러리를 교체할 수 있도록 동적 링크 허용",
        ],
        "restrictions": [
            "수정된 라이브러리는 LGPL로 배포해야 함",
            "정적 링크 시 오브젝트 파일 제공 의무",
        ],
        "ai_training_safe": True,
        "summary_ko": (
            "라이브러리 자체를 수정하면 수정분 소스 공개 필요. "
            "하지만 단순 사용(링크)만 하면 내 코드는 공개 불필요."
        ),
    },
    "LGPL-3.0": {
        "spdx_id": "LGPL-3.0-only",
        "full_name": "GNU Lesser General Public License v3.0",
        "category": "weak_copyleft",
        "osi_approved": True,
        "fsf_free": True,
        "copyleft": "약한 (라이브러리 수정분만)",
        "commercial_use": True,
        "modification": True,
        "distribution": True,
        "private_use": True,
        "patent_grant": True,
        "obligations": [
            "라이브러리 수정 시 소스코드 공개",
            "LGPL 라이브러리임을 고지",
            "사용자의 라이브러리 교체 가능성 보장",
            "설치 정보 제공 (Tivoization 방지, v3 추가 조항)",
        ],
        "restrictions": [
            "수정된 라이브러리는 LGPL-3.0으로 배포",
            "DRM으로 라이브러리 교체 방지 금지 (v3 추가)",
        ],
        "ai_training_safe": True,
        "summary_ko": (
            "LGPL-2.1 + 특허 허여 + DRM 방지. "
            "단순 사용은 자유롭지만 수정 시 소스 공개 의무."
        ),
    },
    "MPL-2.0": {
        "spdx_id": "MPL-2.0",
        "full_name": "Mozilla Public License 2.0",
        "category": "weak_copyleft",
        "osi_approved": True,
        "fsf_free": True,
        "copyleft": "약한 (파일 단위)",
        "commercial_use": True,
        "modification": True,
        "distribution": True,
        "private_use": True,
        "patent_grant": True,
        "obligations": [
            "수정한 파일의 소스코드 공개 (파일 단위 카피레프트)",
            "MPL 고지 유지",
            "변경사항 표시",
        ],
        "restrictions": [
            "수정한 MPL 파일은 MPL-2.0으로 유지",
        ],
        "ai_training_safe": True,
        "summary_ko": (
            "파일 단위 카피레프트 — 수정한 파일만 공개하면 됨. "
            "새로 추가한 파일은 다른 라이선스 사용 가능. GPL/Apache와 호환."
        ),
    },
    "EPL-2.0": {
        "spdx_id": "EPL-2.0",
        "full_name": "Eclipse Public License 2.0",
        "category": "weak_copyleft",
        "osi_approved": True,
        "fsf_free": True,
        "copyleft": "약한 (모듈 단위)",
        "commercial_use": True,
        "modification": True,
        "distribution": True,
        "private_use": True,
        "patent_grant": True,
        "obligations": [
            "수정한 모듈의 소스코드 공개",
            "EPL 고지 유지",
            "특허 소송 시 라이선스 자동 종료",
        ],
        "restrictions": [
            "수정 모듈은 EPL-2.0으로 배포",
            "특허 분쟁 시 라이선스 방어 조항 주의",
        ],
        "ai_training_safe": True,
        "summary_ko": (
            "Eclipse 재단 프로젝트용. 모듈 단위 카피레프트. "
            "v2.0부터 GPL 호환 선택지 추가."
        ),
    },
    "GPL-2.0": {
        "spdx_id": "GPL-2.0-only",
        "full_name": "GNU General Public License v2.0",
        "category": "strong_copyleft",
        "osi_approved": True,
        "fsf_free": True,
        "copyleft": "강한 (전체 파생물)",
        "commercial_use": True,
        "modification": True,
        "distribution": True,
        "private_use": True,
        "patent_grant": False,
        "obligations": [
            "전체 소스코드 공개 (파생 저작물 포함)",
            "GPL-2.0 라이선스로 배포",
            "저작권 고지 유지",
            "소스코드 접근 방법 제공",
        ],
        "restrictions": [
            "파생 저작물 전체가 GPL-2.0 적용 (카피레프트 전파)",
            "독점 소프트웨어와 결합 배포 시 주의",
        ],
        "ai_training_safe": False,
        "summary_ko": (
            "강한 카피레프트. GPL 코드를 사용하면 내 코드도 전체 공개 의무. "
            "상업용 소프트웨어에 포함 시 소스코드 공개 필수."
        ),
    },
    "GPL-3.0": {
        "spdx_id": "GPL-3.0-only",
        "full_name": "GNU General Public License v3.0",
        "category": "strong_copyleft",
        "osi_approved": True,
        "fsf_free": True,
        "copyleft": "강한 (전체 파생물 + DRM 방지)",
        "commercial_use": True,
        "modification": True,
        "distribution": True,
        "private_use": True,
        "patent_grant": True,
        "obligations": [
            "전체 소스코드 공개 (파생 저작물 포함)",
            "GPL-3.0 라이선스로 배포",
            "저작권 고지 유지",
            "설치 정보 제공 (Tivoization 방지)",
            "특허 라이선스 자동 부여",
        ],
        "restrictions": [
            "파생 저작물 전체가 GPL-3.0 적용 (카피레프트 전파)",
            "DRM으로 소프트웨어 수정 방지 금지",
            "Apache-2.0과는 호환되지만 GPL-2.0과는 비호환",
        ],
        "ai_training_safe": False,
        "summary_ko": (
            "GPL-2.0보다 더 강한 보호. DRM 방지 + 특허 허여 추가. "
            "상업용 제품에 포함 시 전체 소스코드 공개 + 설치 정보까지 제공 의무."
        ),
    },
    "AGPL-3.0": {
        "spdx_id": "AGPL-3.0-only",
        "full_name": "GNU Affero General Public License v3.0",
        "category": "strong_copyleft",
        "osi_approved": True,
        "fsf_free": True,
        "copyleft": "강한 (네트워크 사용 포함)",
        "commercial_use": True,
        "modification": True,
        "distribution": True,
        "private_use": True,
        "patent_grant": True,
        "obligations": [
            "전체 소스코드 공개 (파생 저작물 포함)",
            "네트워크로 서비스 제공 시에도 소스코드 공개 (SaaS 조항)",
            "AGPL-3.0 라이선스로 배포",
            "원격 사용자에게도 소스코드 접근 방법 제공",
        ],
        "restrictions": [
            "SaaS/웹 서비스로 제공해도 소스코드 공개 의무 (가장 강력한 카피레프트)",
            "상업용 SaaS에 포함 시 매우 위험",
        ],
        "ai_training_safe": False,
        "summary_ko": (
            "가장 강한 카피레프트. GPL-3.0 + SaaS 조항. "
            "서버에서 실행만 해도 소스코드 공개 의무. "
            "SaaS/웹 서비스에 절대 주의 필요."
        ),
    },
    "CC-BY-4.0": {
        "spdx_id": "CC-BY-4.0",
        "full_name": "Creative Commons Attribution 4.0 International",
        "category": "cc_permissive",
        "osi_approved": False,
        "fsf_free": True,
        "copyleft": "없음",
        "commercial_use": True,
        "modification": True,
        "distribution": True,
        "private_use": True,
        "patent_grant": False,
        "obligations": [
            "원작자 저작자 표시 (Attribution)",
            "변경사항 표시",
        ],
        "restrictions": [
            "소프트웨어에는 사용 부적합 (콘텐츠/데이터용)",
        ],
        "ai_training_safe": True,
        "summary_ko": "콘텐츠/데이터용 가장 자유로운 CC 라이선스. 저작자 표시만 하면 상업적 사용 가능.",
    },
    "CC-BY-SA-4.0": {
        "spdx_id": "CC-BY-SA-4.0",
        "full_name": "Creative Commons Attribution-ShareAlike 4.0 International",
        "category": "cc_copyleft",
        "osi_approved": False,
        "fsf_free": True,
        "copyleft": "동일 조건 (ShareAlike)",
        "commercial_use": True,
        "modification": True,
        "distribution": True,
        "private_use": True,
        "patent_grant": False,
        "obligations": [
            "원작자 저작자 표시",
            "동일 조건(CC-BY-SA) 또는 호환 라이선스로 배포",
        ],
        "restrictions": [
            "파생물도 CC-BY-SA로 배포해야 함 (ShareAlike = 카피레프트)",
        ],
        "ai_training_safe": True,
        "summary_ko": "CC-BY + 동일 조건 배포 의무. Wikipedia가 사용하는 라이선스. 상업적 사용은 가능.",
    },
    "CC-BY-NC-4.0": {
        "spdx_id": "CC-BY-NC-4.0",
        "full_name": "Creative Commons Attribution-NonCommercial 4.0 International",
        "category": "cc_noncommercial",
        "osi_approved": False,
        "fsf_free": False,
        "copyleft": "없음",
        "commercial_use": False,
        "modification": True,
        "distribution": True,
        "private_use": True,
        "patent_grant": False,
        "obligations": [
            "원작자 저작자 표시",
            "비상업적 용도만 허용",
        ],
        "restrictions": [
            "상업적 사용 불가 (NonCommercial)",
        ],
        "ai_training_safe": False,
        "summary_ko": "비상업적 사용만 가능. 회사에서 사용하면 라이선스 위반 가능성 높음.",
    },
    "CC0-1.0": {
        "spdx_id": "CC0-1.0",
        "full_name": "Creative Commons Zero v1.0 Universal",
        "category": "public_domain",
        "osi_approved": False,
        "fsf_free": True,
        "copyleft": "없음",
        "commercial_use": True,
        "modification": True,
        "distribution": True,
        "private_use": True,
        "patent_grant": False,
        "obligations": [],
        "restrictions": [],
        "ai_training_safe": True,
        "summary_ko": "퍼블릭 도메인 헌정. 아무런 제한 없이 사용 가능. 저작자 표시도 불필요.",
    },
    "Unlicense": {
        "spdx_id": "Unlicense",
        "full_name": "The Unlicense",
        "category": "permissive",
        "osi_approved": True,
        "fsf_free": True,
        "copyleft": "없음",
        "commercial_use": True,
        "modification": True,
        "distribution": True,
        "private_use": True,
        "patent_grant": False,
        "obligations": [],
        "restrictions": [
            "보증 없음",
        ],
        "ai_training_safe": True,
        "summary_ko": "퍼블릭 도메인과 동일. 아무런 제한 없이 사용 가능.",
    },
    "Proprietary": {
        "spdx_id": "Proprietary",
        "full_name": "Proprietary / All Rights Reserved",
        "category": "proprietary",
        "osi_approved": False,
        "fsf_free": False,
        "copyleft": "해당 없음",
        "commercial_use": False,
        "modification": False,
        "distribution": False,
        "private_use": False,
        "patent_grant": False,
        "obligations": [
            "별도 라이선스 계약 필요",
            "사용 범위 계약서에 따름",
        ],
        "restrictions": [
            "무단 복제·수정·배포 불가",
            "소스코드 접근 불가 (일반적)",
        ],
        "ai_training_safe": False,
        "summary_ko": "독점 라이선스. 모든 사용에 별도 허가 필요. 무단 사용 시 저작권 침해.",
    },
}

# ══════════════════════════════════════════
#  라이선스 호환성 매트릭스
# ══════════════════════════════════════════
#  FSF 공식 호환성 정보 + Wheeler (2014) 슬라이드 기반
#  "compatible" = 두 라이선스 코드 결합 가능
#  "incompatible" = 결합 불가
#  "one_way" = A→B 방향으로만 가능 (A 코드에 B 라이선스 적용 가능)

COMPATIBILITY_MATRIX: dict[str, dict[str, str]] = {
    "MIT": {
        "MIT": "compatible",
        "Apache-2.0": "compatible",
        "BSD-2-Clause": "compatible",
        "BSD-3-Clause": "compatible",
        "LGPL-2.1": "one_way",
        "LGPL-3.0": "one_way",
        "MPL-2.0": "compatible",
        "GPL-2.0": "one_way",
        "GPL-3.0": "one_way",
        "AGPL-3.0": "one_way",
    },
    "Apache-2.0": {
        "MIT": "compatible",
        "Apache-2.0": "compatible",
        "BSD-2-Clause": "compatible",
        "BSD-3-Clause": "compatible",
        "LGPL-2.1": "incompatible",
        "LGPL-3.0": "one_way",
        "MPL-2.0": "compatible",
        "GPL-2.0": "incompatible",
        "GPL-3.0": "one_way",
        "AGPL-3.0": "one_way",
    },
    "LGPL-2.1": {
        "MIT": "compatible",
        "Apache-2.0": "incompatible",
        "LGPL-2.1": "compatible",
        "LGPL-3.0": "one_way",
        "MPL-2.0": "incompatible",
        "GPL-2.0": "one_way",
        "GPL-3.0": "incompatible",
        "AGPL-3.0": "incompatible",
    },
    "LGPL-3.0": {
        "MIT": "compatible",
        "Apache-2.0": "compatible",
        "LGPL-2.1": "incompatible",
        "LGPL-3.0": "compatible",
        "MPL-2.0": "compatible",
        "GPL-2.0": "incompatible",
        "GPL-3.0": "one_way",
        "AGPL-3.0": "one_way",
    },
    "MPL-2.0": {
        "MIT": "compatible",
        "Apache-2.0": "compatible",
        "BSD-2-Clause": "compatible",
        "BSD-3-Clause": "compatible",
        "LGPL-2.1": "incompatible",
        "LGPL-3.0": "compatible",
        "MPL-2.0": "compatible",
        "GPL-2.0": "one_way",
        "GPL-3.0": "one_way",
        "AGPL-3.0": "one_way",
    },
    "GPL-2.0": {
        "MIT": "compatible",
        "Apache-2.0": "incompatible",
        "BSD-2-Clause": "compatible",
        "BSD-3-Clause": "compatible",
        "LGPL-2.1": "compatible",
        "LGPL-3.0": "incompatible",
        "MPL-2.0": "incompatible",
        "GPL-2.0": "compatible",
        "GPL-3.0": "incompatible",
        "AGPL-3.0": "incompatible",
    },
    "GPL-3.0": {
        "MIT": "compatible",
        "Apache-2.0": "compatible",
        "BSD-2-Clause": "compatible",
        "BSD-3-Clause": "compatible",
        "LGPL-2.1": "incompatible",
        "LGPL-3.0": "compatible",
        "MPL-2.0": "compatible",
        "GPL-2.0": "incompatible",
        "GPL-3.0": "compatible",
        "AGPL-3.0": "one_way",
    },
    "AGPL-3.0": {
        "MIT": "compatible",
        "Apache-2.0": "compatible",
        "BSD-2-Clause": "compatible",
        "BSD-3-Clause": "compatible",
        "LGPL-3.0": "compatible",
        "MPL-2.0": "compatible",
        "GPL-2.0": "incompatible",
        "GPL-3.0": "compatible",
        "AGPL-3.0": "compatible",
    },
}

# ══════════════════════════════════════════
#  라이선스 별칭 매핑 (유연한 입력 대응)
# ══════════════════════════════════════════

LICENSE_ALIASES: dict[str, str] = {
    # MIT variants
    "mit": "MIT", "mit license": "MIT", "the mit license": "MIT",
    # Apache variants
    "apache": "Apache-2.0", "apache 2": "Apache-2.0", "apache 2.0": "Apache-2.0",
    "apache-2": "Apache-2.0", "apache license 2.0": "Apache-2.0",
    # BSD variants
    "bsd": "BSD-3-Clause", "bsd-2": "BSD-2-Clause", "bsd 2": "BSD-2-Clause",
    "bsd-3": "BSD-3-Clause", "bsd 3": "BSD-3-Clause",
    "bsd 2-clause": "BSD-2-Clause", "bsd 3-clause": "BSD-3-Clause",
    "simplified bsd": "BSD-2-Clause", "new bsd": "BSD-3-Clause",
    # ISC
    "isc": "ISC", "isc license": "ISC",
    # LGPL variants
    "lgpl": "LGPL-3.0", "lgpl-2": "LGPL-2.1", "lgpl 2": "LGPL-2.1",
    "lgpl-2.1": "LGPL-2.1", "lgpl 2.1": "LGPL-2.1",
    "lgpl-3": "LGPL-3.0", "lgpl 3": "LGPL-3.0", "lgpl 3.0": "LGPL-3.0",
    # MPL
    "mpl": "MPL-2.0", "mpl-2": "MPL-2.0", "mpl 2": "MPL-2.0",
    "mpl 2.0": "MPL-2.0", "mozilla": "MPL-2.0",
    # EPL
    "epl": "EPL-2.0", "epl-2": "EPL-2.0", "epl 2": "EPL-2.0",
    "eclipse": "EPL-2.0",
    # GPL variants
    "gpl": "GPL-3.0", "gpl-2": "GPL-2.0", "gpl 2": "GPL-2.0",
    "gpl-2.0": "GPL-2.0", "gpl 2.0": "GPL-2.0", "gplv2": "GPL-2.0",
    "gpl-3": "GPL-3.0", "gpl 3": "GPL-3.0",
    "gpl-3.0": "GPL-3.0", "gpl 3.0": "GPL-3.0", "gplv3": "GPL-3.0",
    # AGPL
    "agpl": "AGPL-3.0", "agpl-3": "AGPL-3.0", "agpl 3": "AGPL-3.0",
    "agpl-3.0": "AGPL-3.0", "agpl 3.0": "AGPL-3.0", "agplv3": "AGPL-3.0",
    "affero": "AGPL-3.0",
    # CC variants
    "cc-by": "CC-BY-4.0", "cc by": "CC-BY-4.0", "cc-by-4": "CC-BY-4.0",
    "cc-by-sa": "CC-BY-SA-4.0", "cc by sa": "CC-BY-SA-4.0",
    "cc-by-nc": "CC-BY-NC-4.0", "cc by nc": "CC-BY-NC-4.0",
    "cc0": "CC0-1.0", "cc zero": "CC0-1.0", "public domain": "CC0-1.0",
    # Others
    "unlicense": "Unlicense", "the unlicense": "Unlicense",
    "proprietary": "Proprietary", "all rights reserved": "Proprietary",
    "closed source": "Proprietary", "commercial": "Proprietary",
    "zlib": "Zlib",
    "0bsd": "0BSD",
    "boost": "BSL-1.0", "bsl": "BSL-1.0", "boost software": "BSL-1.0",
}


class LicenseScannerTool(BaseTool):
    """오픈소스 라이선스 분석 도구 (CLO 법무IP처 소속).

    학술 기반: OSI, FSF, SPDX (ISO/IEC 5962:2021),
    Copyleft Theory (Stallman, 1985),
    Van den Brande et al. (2014), Wheeler (2014), Rosen (2004)
    """

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "scan")

        if action == "scan":
            return await self._scan(kwargs)
        elif action == "check":
            return await self._check(kwargs)
        elif action == "compatibility":
            return await self._compatibility(kwargs)
        elif action == "risk":
            return await self._risk(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "scan, check, compatibility, risk 중 하나를 사용하세요."
            )

    # ══════════════════════════════════════════
    #  Action 1: scan — 라이선스 상세 분석
    # ══════════════════════════════════════════

    async def _scan(self, kwargs: dict[str, Any]) -> str:
        """라이선스 이름을 입력받아 의무·제한사항 상세 분석."""
        license_name = kwargs.get("license", kwargs.get("license_name", ""))
        if not license_name:
            categories = {
                "허용적 (Permissive)": "MIT, Apache-2.0, BSD, ISC",
                "약한 카피레프트 (Weak Copyleft)": "LGPL, MPL-2.0, EPL-2.0",
                "강한 카피레프트 (Strong Copyleft)": "GPL-2.0, GPL-3.0, AGPL-3.0",
                "크리에이티브 커먼즈 (CC)": "CC-BY, CC-BY-SA, CC-BY-NC, CC0",
                "독점 (Proprietary)": "Proprietary / 상업용",
            }
            lines = ["라이선스 이름(license)을 입력해주세요.\n"]
            lines.append("### 지원하는 라이선스 카테고리")
            for cat, examples in categories.items():
                lines.append(f"- **{cat}**: {examples}")
            lines.append("\n예시: license_scanner(license=\"MIT\")")
            lines.append("예시: license_scanner(license=\"GPL-3.0\")")
            return "\n".join(lines)

        normalized = self._normalize_license(license_name)
        if normalized not in LICENSE_DB:
            available = ", ".join(sorted(LICENSE_DB.keys()))
            return (
                f"'{license_name}'은(는) 데이터베이스에 없는 라이선스입니다.\n"
                f"지원 라이선스: {available}\n\n"
                "별칭도 지원합니다 (예: 'gpl', 'apache', 'cc-by' 등)"
            )

        info = LICENSE_DB[normalized]

        lines = [f"## {info['full_name']} 라이선스 분석\n"]
        lines.append(f"- SPDX ID: **{info['spdx_id']}**")
        lines.append(f"- 카테고리: **{info['category']}**")
        lines.append(f"- OSI 인증: {'예' if info['osi_approved'] else '아니요'}")
        lines.append(f"- FSF 자유 소프트웨어: {'예' if info['fsf_free'] else '아니요'}")
        lines.append(f"- 카피레프트: **{info['copyleft']}**")
        lines.append(f"- AI 학습 데이터 사용: {'안전' if info['ai_training_safe'] else '위험/확인 필요'}\n")

        # 권한 표
        lines.append("### 허용 사항")
        lines.append("| 항목 | 허용 |")
        lines.append("|------|:----:|")
        lines.append(f"| 상업적 사용 | {'허용' if info['commercial_use'] else '불가'} |")
        lines.append(f"| 수정 | {'허용' if info['modification'] else '불가'} |")
        lines.append(f"| 배포 | {'허용' if info['distribution'] else '불가'} |")
        lines.append(f"| 개인 사용 | {'허용' if info['private_use'] else '불가'} |")
        lines.append(f"| 특허 허여 | {'포함' if info['patent_grant'] else '미포함'} |")

        # 의무사항
        if info["obligations"]:
            lines.append("\n### 의무사항 (반드시 준수)")
            for i, obl in enumerate(info["obligations"], 1):
                lines.append(f"  {i}. {obl}")

        # 제한사항
        if info["restrictions"]:
            lines.append("\n### 제한사항 (주의)")
            for i, rst in enumerate(info["restrictions"], 1):
                lines.append(f"  {i}. {rst}")

        lines.append(f"\n### 요약")
        lines.append(f"{info['summary_ko']}")

        formatted = "\n".join(lines)

        # LLM 상세 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 오픈소스 라이선스 전문 변호사입니다.\n"
                "OSI, FSF, SPDX 표준 기반으로 라이선스를 분석합니다.\n\n"
                "다음 라이선스 정보를 바탕으로 실무적 조언을 제시하세요:\n\n"
                "1. **실무 사용 가이드**: 이 라이선스의 소프트웨어를 사용할 때 구체적으로 할 일\n"
                "2. **흔한 실수**: 개발자들이 자주 하는 라이선스 위반 사례\n"
                "3. **기업 사용 시 주의점**: 상업적 제품에 포함할 때 리스크\n"
                "4. **대안 라이선스**: 비슷하지만 더 적합할 수 있는 라이선스\n\n"
                "한국어로, 비개발자(CEO)가 이해할 수 있게 쉽게 설명하세요."
            ),
            user_prompt=f"라이선스 분석 결과:\n\n{formatted}",
        )

        return f"{formatted}\n\n---\n\n## 전문가 의견\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  Action 2: check — 라이선스 준수 확인
    # ══════════════════════════════════════════

    async def _check(self, kwargs: dict[str, Any]) -> str:
        """특정 사용 시나리오의 라이선스 준수 여부 확인."""
        license_name = kwargs.get("license", kwargs.get("license_name", ""))
        usage = kwargs.get("usage", "")

        if not license_name:
            return (
                "라이선스 이름(license)과 사용 시나리오(usage)를 입력해주세요.\n"
                "예시: license_scanner(action=\"check\", license=\"MIT\", "
                "usage=\"SaaS 서비스에 포함하여 유료 판매\")"
            )

        normalized = self._normalize_license(license_name)
        if normalized not in LICENSE_DB:
            return f"'{license_name}'은(는) 데이터베이스에 없는 라이선스입니다."

        info = LICENSE_DB[normalized]

        # 기본 준수 체크
        checks = []
        usage_lower = usage.lower()

        # 상업적 사용 체크
        commercial_keywords = ["상업", "유료", "판매", "수익", "commercial", "비즈니스", "영리"]
        is_commercial = any(kw in usage_lower for kw in commercial_keywords)
        if is_commercial and not info["commercial_use"]:
            checks.append({
                "status": "위반",
                "item": "상업적 사용",
                "detail": f"{normalized} 라이선스는 상업적 사용을 허용하지 않습니다.",
            })
        elif is_commercial and info["commercial_use"]:
            checks.append({
                "status": "준수",
                "item": "상업적 사용",
                "detail": "상업적 사용 허용됨.",
            })

        # SaaS/서버 체크 (AGPL 주의)
        saas_keywords = ["saas", "서버", "웹서비스", "api", "클라우드", "server"]
        is_saas = any(kw in usage_lower for kw in saas_keywords)
        if is_saas and normalized == "AGPL-3.0":
            checks.append({
                "status": "위험",
                "item": "SaaS/서버 사용",
                "detail": "AGPL-3.0은 서버에서 실행해도 소스코드 공개 의무. SaaS에 매우 위험.",
            })
        elif is_saas and info["category"] == "strong_copyleft":
            checks.append({
                "status": "주의",
                "item": "SaaS/서버 사용",
                "detail": f"{normalized}는 강한 카피레프트. 서버에서 실행만 하면 소스코드 공개 의무가 발생할 수 있음.",
            })

        # 배포 체크
        dist_keywords = ["배포", "공개", "출시", "릴리스", "distribute", "publish"]
        is_dist = any(kw in usage_lower for kw in dist_keywords)
        if is_dist and info["category"] in ("strong_copyleft", "weak_copyleft"):
            checks.append({
                "status": "주의",
                "item": "배포 시 카피레프트",
                "detail": f"{normalized}는 카피레프트({info['copyleft']}). 배포 시 소스코드 공개 의무 확인 필요.",
            })

        # 수정 체크
        mod_keywords = ["수정", "변경", "커스텀", "포크", "fork", "modify"]
        is_mod = any(kw in usage_lower for kw in mod_keywords)
        if is_mod and not info["modification"]:
            checks.append({
                "status": "위반",
                "item": "수정",
                "detail": f"{normalized}는 수정을 허용하지 않습니다.",
            })

        # 의무사항 리마인드
        if info["obligations"]:
            checks.append({
                "status": "확인",
                "item": "의무사항",
                "detail": "다음 의무를 반드시 이행하세요: " + "; ".join(info["obligations"]),
            })

        # 결과 포맷
        lines = [f"## {info['full_name']} 준수 확인\n"]
        lines.append(f"- 사용 시나리오: **{usage or '(미입력)'}**\n")

        lines.append("### 준수 체크 결과")
        for c in checks:
            status_label = {
                "준수": "[준수]",
                "위반": "[위반]",
                "위험": "[위험]",
                "주의": "[주의]",
                "확인": "[확인]",
            }.get(c["status"], "[정보]")
            lines.append(f"- {status_label} **{c['item']}**: {c['detail']}")

        formatted = "\n".join(lines)

        # LLM 종합 판단
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 오픈소스 라이선스 컴플라이언스 전문가입니다.\n"
                "라이선스 준수 체크 결과를 바탕으로 다음을 제시하세요:\n\n"
                "1. **종합 판정**: 이 사용 시나리오가 라이선스를 준수하는지 (준수/위반/위험)\n"
                "2. **구체적 이행 사항**: 준수를 위해 실제로 해야 할 일\n"
                "3. **위반 시 리스크**: 라이선스 위반 시 발생할 수 있는 법적 결과\n"
                "4. **대안 방안**: 위반 위험이 있다면 안전한 대안\n\n"
                "한국어로, 비개발자(CEO)가 이해할 수 있게 쉽게 설명하세요."
            ),
            user_prompt=f"라이선스 준수 확인 결과:\n\n{formatted}",
        )

        return f"{formatted}\n\n---\n\n## 전문가 판정\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  Action 3: compatibility — 호환성 검사
    # ══════════════════════════════════════════

    async def _compatibility(self, kwargs: dict[str, Any]) -> str:
        """두 라이선스 간 호환성 검사."""
        license1 = kwargs.get("license1", "")
        license2 = kwargs.get("license2", "")

        if not license1 or not license2:
            return (
                "두 라이선스(license1, license2)를 입력해주세요.\n"
                "예시: license_scanner(action=\"compatibility\", "
                "license1=\"MIT\", license2=\"GPL-3.0\")"
            )

        norm1 = self._normalize_license(license1)
        norm2 = self._normalize_license(license2)

        if norm1 not in LICENSE_DB:
            return f"'{license1}'은(는) 데이터베이스에 없는 라이선스입니다."
        if norm2 not in LICENSE_DB:
            return f"'{license2}'은(는) 데이터베이스에 없는 라이선스입니다."

        # 호환성 확인
        compat = self._check_compatibility(norm1, norm2)

        info1 = LICENSE_DB[norm1]
        info2 = LICENSE_DB[norm2]

        lines = [f"## 라이선스 호환성 검사\n"]
        lines.append(f"- 라이선스 1: **{info1['full_name']}** ({info1['category']})")
        lines.append(f"- 라이선스 2: **{info2['full_name']}** ({info2['category']})\n")

        compat_label = {
            "compatible": "[호환] 두 라이선스 코드를 결합할 수 있습니다.",
            "incompatible": "[비호환] 두 라이선스 코드를 결합할 수 없습니다.",
            "one_way": "[단방향 호환] 한 방향으로만 결합 가능합니다.",
            "unknown": "[미확인] 호환성 데이터가 없습니다. 전문가 확인 필요.",
        }
        lines.append(f"### 호환성 결과: {compat_label.get(compat, compat_label['unknown'])}\n")

        # 비교표
        lines.append("### 라이선스 비교표")
        lines.append("| 항목 | " + info1['spdx_id'] + " | " + info2['spdx_id'] + " |")
        lines.append("|------|" + "-" * (len(info1['spdx_id']) + 2) + "|" + "-" * (len(info2['spdx_id']) + 2) + "|")
        lines.append(f"| 카테고리 | {info1['category']} | {info2['category']} |")
        lines.append(f"| 카피레프트 | {info1['copyleft']} | {info2['copyleft']} |")
        lines.append(f"| 상업적 사용 | {'허용' if info1['commercial_use'] else '불가'} | {'허용' if info2['commercial_use'] else '불가'} |")
        lines.append(f"| 특허 허여 | {'포함' if info1['patent_grant'] else '미포함'} | {'포함' if info2['patent_grant'] else '미포함'} |")
        lines.append(f"| AI 학습 안전 | {'안전' if info1['ai_training_safe'] else '위험'} | {'안전' if info2['ai_training_safe'] else '위험'} |")

        formatted = "\n".join(lines)

        # LLM 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 오픈소스 라이선스 호환성 전문가입니다.\n"
                "FSF 공식 호환성 매트릭스와 Wheeler(2014) 분석 기반으로\n"
                "두 라이선스의 호환성을 상세히 설명하세요.\n\n"
                "1. **결합 가능 방법**: 어떤 방식으로 코드를 결합할 수 있는지\n"
                "2. **비호환 시 우회 방안**: 결합 불가 시 대안 (동적 링크, 별도 프로세스 등)\n"
                "3. **실무 권고사항**: 프로젝트에서 이 두 라이선스를 함께 사용할 때 주의사항\n"
                "4. **카피레프트 전파 위험**: 강한 카피레프트가 약한 라이선스를 덮어쓰는지\n\n"
                "한국어로, 비개발자(CEO)가 이해할 수 있게 쉽게 설명하세요."
            ),
            user_prompt=f"호환성 검사 결과:\n\n{formatted}",
        )

        return f"{formatted}\n\n---\n\n## 전문가 호환성 분석\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  Action 4: risk — 프로젝트 라이선스 종합 리스크
    # ══════════════════════════════════════════

    async def _risk(self, kwargs: dict[str, Any]) -> str:
        """프로젝트 내 라이선스 조합의 종합 리스크 분석."""
        licenses_input = kwargs.get("licenses", "")

        if not licenses_input:
            return (
                "프로젝트에서 사용하는 라이선스 목록(licenses)을 쉼표로 구분하여 입력해주세요.\n"
                "예시: license_scanner(action=\"risk\", "
                "licenses=\"MIT, Apache-2.0, GPL-3.0, LGPL-2.1\")"
            )

        # 라이선스 파싱 및 정규화
        license_list = self._parse_license_list(licenses_input)
        if not license_list:
            return "입력된 라이선스를 인식할 수 없습니다. SPDX ID 또는 일반명으로 입력해주세요."

        # 카테고리별 분류
        category_count: dict[str, list[str]] = {}
        unknown_licenses: list[str] = []

        for lic in license_list:
            normalized = self._normalize_license(lic)
            if normalized in LICENSE_DB:
                cat = LICENSE_DB[normalized]["category"]
                category_count.setdefault(cat, []).append(normalized)
            else:
                unknown_licenses.append(lic)

        # 리스크 평가
        risks: list[dict[str, str]] = []
        risk_score = 0

        # 1) 강한 카피레프트 존재 여부
        strong_copylefts = category_count.get("strong_copyleft", [])
        if strong_copylefts:
            risk_score += 30
            risks.append({
                "level": "높음",
                "item": "강한 카피레프트 감지",
                "detail": (
                    f"{', '.join(strong_copylefts)} — "
                    "전체 소스코드 공개 의무 발생 가능. "
                    "상업적 제품 포함 시 즉각 법률 검토 필요."
                ),
            })

        # 2) AGPL 특별 경고
        if "AGPL-3.0" in strong_copylefts:
            risk_score += 20
            risks.append({
                "level": "높음",
                "item": "AGPL-3.0 감지 (SaaS 위험)",
                "detail": (
                    "AGPL-3.0은 서버에서 실행만 해도 소스코드 공개 의무. "
                    "SaaS/웹 서비스에 포함 시 매우 위험."
                ),
            })

        # 3) 약한 카피레프트 존재 여부
        weak_copylefts = category_count.get("weak_copyleft", [])
        if weak_copylefts:
            risk_score += 10
            risks.append({
                "level": "중간",
                "item": "약한 카피레프트 감지",
                "detail": (
                    f"{', '.join(weak_copylefts)} — "
                    "수정분 소스코드 공개 의무. 단순 사용은 안전하지만 수정 시 주의."
                ),
            })

        # 4) 비상업적 라이선스 존재
        nc_licenses = category_count.get("cc_noncommercial", []) + category_count.get("cc_nc_copyleft", []) + category_count.get("cc_nc_nd", [])
        if nc_licenses:
            risk_score += 25
            risks.append({
                "level": "높음",
                "item": "비상업적(NC) 라이선스 감지",
                "detail": (
                    f"{', '.join(nc_licenses)} — "
                    "상업적 사용 불가. 회사 프로젝트에 사용 시 라이선스 위반."
                ),
            })

        # 5) 호환성 충돌 체크
        all_normalized = []
        for lic in license_list:
            n = self._normalize_license(lic)
            if n in LICENSE_DB:
                all_normalized.append(n)

        conflicts = []
        checked_pairs: set[tuple[str, str]] = set()
        for i, l1 in enumerate(all_normalized):
            for j, l2 in enumerate(all_normalized):
                if i >= j:
                    continue
                pair = (min(l1, l2), max(l1, l2))
                if pair in checked_pairs:
                    continue
                checked_pairs.add(pair)
                compat = self._check_compatibility(l1, l2)
                if compat == "incompatible":
                    conflicts.append((l1, l2))

        if conflicts:
            risk_score += 20 * len(conflicts)
            for l1, l2 in conflicts:
                risks.append({
                    "level": "높음",
                    "item": f"호환성 충돌: {l1} vs {l2}",
                    "detail": (
                        f"{l1}과 {l2}는 호환되지 않습니다. "
                        "두 라이선스의 코드를 결합하여 배포할 수 없음."
                    ),
                })

        # 6) 독점 라이선스 존재
        proprietary = category_count.get("proprietary", [])
        if proprietary:
            risk_score += 15
            risks.append({
                "level": "중간",
                "item": "독점 라이선스 감지",
                "detail": "Proprietary 라이선스는 별도 계약 조건 확인 필요.",
            })

        # 위험도 등급
        if risk_score >= 50:
            grade = "위험 (법률 검토 필수)"
        elif risk_score >= 25:
            grade = "주의 (일부 항목 확인 필요)"
        elif risk_score >= 10:
            grade = "양호 (경미한 확인 사항)"
        else:
            grade = "안전 (허용적 라이선스만 사용)"

        lines = ["## 프로젝트 라이선스 종합 리스크 분석\n"]
        lines.append(f"- 분석 대상: **{len(license_list)}개** 라이선스")
        lines.append(f"- 리스크 점수: **{risk_score}점**")
        lines.append(f"- 리스크 등급: **{grade}**\n")

        # 카테고리 분포
        lines.append("### 라이선스 분포")
        cat_names = {
            "permissive": "허용적 (Permissive)",
            "weak_copyleft": "약한 카피레프트",
            "strong_copyleft": "강한 카피레프트",
            "cc_permissive": "CC 허용적",
            "cc_copyleft": "CC 카피레프트",
            "cc_noncommercial": "CC 비상업적",
            "cc_nc_copyleft": "CC 비상업적+카피레프트",
            "cc_noderivatives": "CC 변경금지",
            "cc_nc_nd": "CC 비상업적+변경금지",
            "public_domain": "퍼블릭 도메인",
            "proprietary": "독점",
        }
        for cat, lics in category_count.items():
            name = cat_names.get(cat, cat)
            lines.append(f"- **{name}**: {', '.join(lics)}")

        if unknown_licenses:
            lines.append(f"- **미인식**: {', '.join(unknown_licenses)}")

        # 리스크 항목
        if risks:
            lines.append("\n### 리스크 항목")
            for r in risks:
                level_label = {"높음": "[위험]", "중간": "[주의]", "낮음": "[참고]"}.get(r["level"], "[정보]")
                lines.append(f"\n{level_label} **{r['item']}**")
                lines.append(f"  {r['detail']}")

        # 호환성 충돌 요약
        if conflicts:
            lines.append("\n### 호환성 충돌 목록")
            for l1, l2 in conflicts:
                lines.append(f"  - {l1} vs {l2}: **비호환** (결합 배포 불가)")

        formatted = "\n".join(lines)

        # LLM 종합 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 오픈소스 라이선스 컴플라이언스 전문 변호사입니다.\n"
                "프로젝트의 라이선스 조합 리스크를 분석하여 다음을 제시하세요:\n\n"
                "1. **종합 위험도 판정**: 이 프로젝트의 라이선스 조합이 안전한지\n"
                "2. **즉시 조치 사항**: 바로 해결해야 할 라이선스 문제\n"
                "3. **카피레프트 전파 경로**: 강한 카피레프트가 다른 코드에 영향을 미치는 경로\n"
                "4. **대체 라이브러리 추천**: 문제 라이선스를 대체할 수 있는 라이브러리 방향\n"
                "5. **라이선스 준수 체크리스트**: CEO가 확인해야 할 항목\n\n"
                "한국어로, 비개발자(CEO)가 이해할 수 있게 쉽게 설명하세요."
            ),
            user_prompt=f"프로젝트 라이선스 리스크 분석 결과:\n\n{formatted}",
        )

        return f"{formatted}\n\n---\n\n## 전문가 종합 의견\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  내부 유틸리티 메서드
    # ══════════════════════════════════════════

    @staticmethod
    def _normalize_license(name: str) -> str:
        """라이선스 이름을 SPDX ID로 정규화."""
        stripped = name.strip()
        # 정확한 SPDX ID 매칭
        if stripped in LICENSE_DB:
            return stripped
        # 별칭 매칭
        lower = stripped.lower()
        if lower in LICENSE_ALIASES:
            return LICENSE_ALIASES[lower]
        # 부분 매칭 시도
        for alias, spdx in LICENSE_ALIASES.items():
            if alias in lower or lower in alias:
                return spdx
        return stripped

    @staticmethod
    def _parse_license_list(text: str) -> list[str]:
        """쉼표/공백/줄바꿈으로 구분된 라이선스 목록 파싱."""
        # 쉼표로 먼저 분리, 그 다음 줄바꿈
        parts = []
        for segment in text.split(","):
            segment = segment.strip()
            if segment:
                parts.append(segment)
        if not parts:
            for segment in text.split("\n"):
                segment = segment.strip()
                if segment:
                    parts.append(segment)
        return parts

    @staticmethod
    def _check_compatibility(license1: str, license2: str) -> str:
        """두 라이선스의 호환성을 확인."""
        if license1 in COMPATIBILITY_MATRIX:
            row = COMPATIBILITY_MATRIX[license1]
            if license2 in row:
                return row[license2]
        if license2 in COMPATIBILITY_MATRIX:
            row = COMPATIBILITY_MATRIX[license2]
            if license1 in row:
                result = row[license1]
                # one_way는 방향이 반대
                if result == "one_way":
                    return "one_way"
                return result
        return "unknown"
