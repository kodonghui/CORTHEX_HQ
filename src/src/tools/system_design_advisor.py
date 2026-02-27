"""
시스템 설계 자문 도구 (System Design Advisor) — 교수급 시스템 아키텍처 설계를 자문합니다.

CAP 정리, 확장성 패턴, 데이터 저장소 선택, 통신 아키텍처, 장애 복원,
보안 아키텍처, 관측성 설계를 종합적으로 분석하여
실제 프로덕션 시스템에 적용 가능한 수준의 설계 가이드를 제공합니다.

학술 근거:
  - Eric Brewer, "CAP Theorem" (2000) — 분산 시스템의 일관성·가용성·분할 내성 트레이드오프
  - Martin Kleppmann, "Designing Data-Intensive Applications" (O'Reilly, 2017) — 데이터 중심 설계 바이블
  - Michael Nygard, "Release It! 2nd Ed." (Pragmatic, 2018) — 안정적 프로덕션 패턴
  - Google SRE Book, "Site Reliability Engineering" (O'Reilly, 2016) — 관측성·SLO 프레임워크

사용 방법:
  - action="design"         : 시스템 설계 종합 자문 (CAP 정리 기반)
  - action="scalability"    : 확장성 패턴 분석 (수평/수직/캐싱/CDN/샤딩)
  - action="datastore"      : 데이터 저장소 선택 자문 (SQL vs NoSQL vs NewSQL vs TimeSeries)
  - action="communication"  : 통신 패턴 비교 분석 (REST/gRPC/GraphQL/WebSocket/MQ)
  - action="reliability"    : 신뢰성 설계 자문 (Circuit Breaker, Retry, Bulkhead, Failover)
  - action="security"       : 보안 아키텍처 자문 (Zero Trust, OAuth2, mTLS, Vault)
  - action="observability"  : 관측성 설계 자문 (Metrics/Logs/Traces — 3 Pillars)
  - action="full"           : 전체 종합 (7개 분석 asyncio.gather 병렬)

필요 환경변수: 없음 (LLM 호출만 사용)
필요 라이브러리: 없음 (표준 라이브러리만 사용)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.system_design_advisor")

# ─── CAP 정리 프레임워크 (Eric Brewer, 2000) ──────────────────────

_CAP_THEOREM: dict[str, dict] = {
    "Consistency": {
        "desc": "일관성 — 모든 노드가 동일한 데이터를 동시에 반환",
        "trade_off": "가용성(A) 또는 분할 내성(P) 중 하나를 희생",
        "use_case": "금융 거래, 재고 관리, 결제 시스템",
    },
    "Availability": {
        "desc": "가용성 — 모든 요청에 대해 (장애가 아닌) 응답을 보장",
        "trade_off": "일관성(C) 또는 분할 내성(P) 중 하나를 희생",
        "use_case": "소셜 피드, 검색 엔진, 콘텐츠 배포",
    },
    "Partition_Tolerance": {
        "desc": "분할 내성 — 네트워크 분할 시에도 시스템이 동작",
        "trade_off": "분산 시스템에서 P는 사실상 필수; C와 A 사이 선택",
        "use_case": "분산 시스템 전반 (네트워크 장애는 불가피)",
    },
    "CP_Systems": {
        "desc": "CP 조합 — 일관성 + 분할 내성 (가용성 희생)",
        "examples": "MongoDB (strong read), HBase, Redis Cluster, Zookeeper",
        "when": "데이터 정확성이 최우선인 시스템 (금융, 예약)",
    },
    "AP_Systems": {
        "desc": "AP 조합 — 가용성 + 분할 내성 (일관성 희생, 최종 일관성)",
        "examples": "Cassandra, DynamoDB, CouchDB, Riak",
        "when": "항상 응답해야 하는 시스템 (SNS, DNS, CDN)",
    },
    "CA_Systems": {
        "desc": "CA 조합 — 일관성 + 가용성 (분할 내성 없음, 단일 노드)",
        "examples": "단일 PostgreSQL, 단일 MySQL, SQLite",
        "when": "네트워크 분할이 없는 단일 서버 환경",
    },
}

# ─── 확장성 패턴 (Kleppmann, 2017) ─────────────────────────────

_SCALABILITY_PATTERNS: dict[str, dict] = {
    "horizontal_scaling": {
        "name": "수평 확장 (Scale-Out)",
        "desc": "서버 인스턴스를 추가하여 부하 분산",
        "pros": "이론적 무한 확장, 단일 장애점 제거, 비용 효율적",
        "cons": "데이터 일관성 복잡, 세션 관리 필요, 네트워크 오버헤드",
        "tools": "Kubernetes, Docker Swarm, AWS Auto Scaling, Load Balancer",
        "best_for": "Stateless 웹서버, API 게이트웨이, 마이크로서비스",
    },
    "vertical_scaling": {
        "name": "수직 확장 (Scale-Up)",
        "desc": "단일 서버의 CPU/RAM/디스크를 증설",
        "pros": "구현 단순, 데이터 일관성 보장, 운영 복잡도 낮음",
        "cons": "물리적 한계 존재, 단일 장애점, 비용 급증 곡선",
        "tools": "AWS EC2 인스턴스 타입 변경, 클라우드 VM 리사이징",
        "best_for": "단일 DB 서버, 레거시 모놀리식, 초기 MVP",
    },
    "caching": {
        "name": "캐싱 전략",
        "desc": "자주 접근하는 데이터를 메모리에 적재하여 응답 속도 향상",
        "pros": "읽기 성능 극대화 (10~100배), DB 부하 감소, 비용 절감",
        "cons": "캐시 무효화 복잡, 메모리 비용, 데이터 불일치 가능",
        "tools": "Redis, Memcached, Varnish, CDN Edge Cache, 브라우저 캐시",
        "best_for": "읽기 비중 높은 서비스 (뉴스, 카탈로그, 프로필)",
    },
    "cdn": {
        "name": "CDN (Content Delivery Network)",
        "desc": "전 세계 엣지 서버에 정적 콘텐츠를 분산 배치",
        "pros": "글로벌 지연 시간 감소, DDoS 완화, 오리진 부하 감소",
        "cons": "동적 콘텐츠 한계, 캐시 퍼지 지연, 추가 비용",
        "tools": "Cloudflare, AWS CloudFront, Fastly, Akamai",
        "best_for": "정적 에셋 (이미지, JS, CSS), 미디어 스트리밍, SPA",
    },
    "sharding": {
        "name": "샤딩 (Sharding)",
        "desc": "데이터를 수평으로 분할하여 여러 DB 인스턴스에 분산 저장",
        "pros": "DB 용량 무한 확장, 쿼리 병렬화, 장애 격리",
        "cons": "JOIN 어려움, 리밸런싱 복잡, 핫스팟 가능성",
        "tools": "Vitess, CockroachDB, MongoDB Sharding, Citus (PostgreSQL)",
        "best_for": "대규모 데이터셋 (수억 레코드), 멀티테넌트 SaaS",
    },
}

# ─── 데이터 저장소 비교 (Kleppmann, 2017) ──────────────────────

_DATA_STORES: dict[str, dict] = {
    "RDBMS": {
        "name": "관계형 DB (RDBMS)",
        "examples": "PostgreSQL, MySQL, Oracle, SQL Server",
        "strengths": "ACID 보장, SQL 표준, JOIN/트랜잭션, 스키마 무결성",
        "weaknesses": "수평 확장 어려움, 스키마 변경 부담, 비정형 데이터 한계",
        "best_for": "트랜잭션 중심 (금융, ERP, CRM), 정규화된 관계 데이터",
        "cap": "CA (단일) / CP (Galera, Patroni 클러스터)",
        "scale": "수직 확장 우선, 읽기 레플리카로 읽기 확장",
    },
    "Document": {
        "name": "문서형 DB (Document Store)",
        "examples": "MongoDB, CouchDB, Amazon DocumentDB, Firestore",
        "strengths": "유연한 스키마, 중첩 구조 자연스러움, 수평 확장 용이",
        "weaknesses": "JOIN 비효율, 트랜잭션 제한적, 데이터 중복 발생",
        "best_for": "콘텐츠 관리, 사용자 프로필, 카탈로그, 이벤트 로그",
        "cap": "CP (strong read) 또는 AP (eventual consistency)",
        "scale": "샤딩 기본 지원, 레플리카셋",
    },
    "KeyValue": {
        "name": "키-값 저장소 (Key-Value Store)",
        "examples": "Redis, Memcached, DynamoDB, etcd, Riak",
        "strengths": "극단적 저지연 (sub-ms), 단순한 API, 수평 확장 용이",
        "weaknesses": "범위 쿼리 제한, 관계 표현 불가, 값 크기 제약",
        "best_for": "세션 저장, 캐싱, 속도 제한기, 실시간 순위표",
        "cap": "AP (DynamoDB, Riak) 또는 CP (etcd, Redis Cluster)",
        "scale": "해시 기반 파티셔닝, 클러스터 모드",
    },
    "Column": {
        "name": "컬럼형 DB (Wide-Column Store)",
        "examples": "Cassandra, HBase, ScyllaDB, Google Bigtable",
        "strengths": "대규모 쓰기 성능, 시계열 최적, 수평 확장 탁월",
        "weaknesses": "복잡한 데이터 모델링, 읽기 패턴 제약, 학습 곡선",
        "best_for": "IoT 시계열, 로그 수집, 메시징 이력, 대규모 분석",
        "cap": "AP (Cassandra) 또는 CP (HBase)",
        "scale": "링 토폴로지 샤딩, 자동 리밸런싱",
    },
    "Graph": {
        "name": "그래프 DB (Graph Database)",
        "examples": "Neo4j, Amazon Neptune, ArangoDB, JanusGraph",
        "strengths": "관계 탐색 최적, 패턴 매칭, 추천·사기탐지에 탁월",
        "weaknesses": "대규모 집계 느림, 에코시스템 제한적, 샤딩 어려움",
        "best_for": "소셜 네트워크, 추천 시스템, 지식 그래프, 사기 탐지",
        "cap": "CA (단일 Neo4j) / CP (Causal Cluster)",
        "scale": "읽기 레플리카, Fabric (페더레이션)",
    },
    "TimeSeries": {
        "name": "시계열 DB (Time-Series Database)",
        "examples": "InfluxDB, TimescaleDB, QuestDB, Prometheus (TSDB)",
        "strengths": "시간 기반 쿼리 최적화, 자동 다운샘플링, 높은 쓰기 처리량",
        "weaknesses": "범용 쿼리 한계, UPDATE 비효율, 관계 모델링 불가",
        "best_for": "모니터링 메트릭, IoT 센서, 주가 데이터, 서버 로그",
        "cap": "CP (InfluxDB 클러스터) / CA (TimescaleDB 단일)",
        "scale": "시간 기반 파티셔닝, 자동 보존 정책",
    },
}

# ─── 통신 패턴 비교 ────────────────────────────────────────

_COMMUNICATION_PATTERNS: dict[str, dict] = {
    "REST": {
        "name": "REST (Representational State Transfer)",
        "protocol": "HTTP/1.1 또는 HTTP/2",
        "format": "JSON (일반적), XML",
        "strengths": "범용성, 브라우저 호환, 캐싱 용이, 생태계 풍부",
        "weaknesses": "Over-fetching/Under-fetching, N+1 문제, 실시간 불가",
        "latency": "중간 (10~100ms)",
        "best_for": "CRUD API, 공개 API, 모바일 앱 백엔드",
    },
    "gRPC": {
        "name": "gRPC (Google Remote Procedure Call)",
        "protocol": "HTTP/2 + Protocol Buffers",
        "format": "Protobuf (바이너리)",
        "strengths": "고성능 (바이너리 직렬화), 양방향 스트리밍, 코드 자동 생성",
        "weaknesses": "브라우저 직접 호출 불가, 디버깅 어려움, 학습 곡선",
        "latency": "낮음 (1~10ms)",
        "best_for": "마이크로서비스 간 통신, 실시간 스트리밍, 내부 API",
    },
    "GraphQL": {
        "name": "GraphQL",
        "protocol": "HTTP (단일 엔드포인트)",
        "format": "JSON",
        "strengths": "클라이언트 주도 쿼리, Over-fetching 제거, 타입 시스템",
        "weaknesses": "캐싱 복잡, N+1 쿼리 문제, 파일 업로드 불편",
        "latency": "중간 (10~50ms)",
        "best_for": "복잡한 프론트엔드, 다양한 클라이언트, BFF 패턴",
    },
    "WebSocket": {
        "name": "WebSocket",
        "protocol": "WS/WSS (TCP 기반 양방향)",
        "format": "자유 (JSON, 바이너리 등)",
        "strengths": "실시간 양방향 통신, 낮은 오버헤드, 서버 푸시",
        "weaknesses": "상태 유지 필요, 로드밸런싱 복잡, 재연결 로직 필요",
        "latency": "매우 낮음 (<1ms 핸드셰이크 후)",
        "best_for": "채팅, 실시간 대시보드, 게임, 협업 도구",
    },
    "MessageQueue": {
        "name": "메시지 큐 (Message Queue)",
        "protocol": "AMQP, MQTT, 또는 독자 프로토콜",
        "format": "자유 (JSON, Protobuf, Avro 등)",
        "strengths": "비동기 디커플링, 버퍼링, 재시도 내장, 피크 완충",
        "weaknesses": "디버깅 어려움, 순서 보장 복잡, 지연 발생",
        "latency": "가변 (ms~s, 비동기)",
        "best_for": "이벤트 기반 아키텍처, 작업 큐, 마이크로서비스 통합",
    },
}

# ─── 신뢰성 패턴 (Nygard, "Release It!" 2018) ────────────────

_RELIABILITY_PATTERNS: dict[str, dict] = {
    "circuit_breaker": {
        "name": "서킷 브레이커 (Circuit Breaker)",
        "desc": "연속 실패 시 회로를 차단하여 장애 전파를 방지",
        "states": "CLOSED (정상) → OPEN (차단) → HALF-OPEN (시험적 허용)",
        "config": "실패 임계값 (예: 5회/10초), 차단 시간 (예: 30초), 반열림 시도 수",
        "tools": "Resilience4j, Hystrix (deprecated), Polly (.NET), pybreaker",
        "example": "외부 결제 API 장애 시 → 차단 → 폴백 결제 안내 → 복구 시 자동 재개",
    },
    "retry_with_backoff": {
        "name": "재시도 + 지수 백오프 (Retry with Exponential Backoff)",
        "desc": "일시적 장애에 대해 간격을 점차 늘리며 재시도",
        "config": "최대 재시도 횟수, 초기 간격, 백오프 승수, 최대 간격, 지터(jitter)",
        "formula": "delay = min(initial * (multiplier ^ attempt) + random_jitter, max_delay)",
        "tools": "tenacity (Python), retry (Go), Spring Retry, AWS SDK 내장",
        "example": "DB 커넥션 실패 → 100ms → 200ms → 400ms → 800ms (+ 랜덤 지터)",
    },
    "bulkhead": {
        "name": "벌크헤드 (Bulkhead — 격벽 패턴)",
        "desc": "리소스를 격리하여 하나의 장애가 전체 시스템을 마비시키지 않게 함",
        "types": "스레드 풀 격벽, 세마포어 격벽, 프로세스 격벽",
        "config": "풀 크기, 대기 큐 크기, 타임아웃",
        "tools": "Resilience4j Bulkhead, Istio (사이드카), Kubernetes 리소스 제한",
        "example": "결제 서비스와 검색 서비스의 스레드 풀을 분리 → 검색 과부하가 결제에 영향 없음",
    },
    "failover": {
        "name": "페일오버 (Failover — 자동 장애 전환)",
        "desc": "주 시스템 장애 시 대기 시스템으로 자동 전환",
        "types": "Active-Passive (Cold/Warm Standby), Active-Active (Hot Standby), Multi-Region",
        "metrics": "RTO (복구 목표 시간), RPO (복구 목표 시점), MTTR (평균 복구 시간)",
        "tools": "AWS Multi-AZ, Patroni (PostgreSQL), Redis Sentinel, DNS Failover",
        "example": "Primary DB 다운 → Replica 자동 승격 (RTO < 30초) → 앱 자동 재연결",
    },
}

# ─── 학술 참고 문헌 상수 ──────────────────────────────────────

_REFERENCES = (
    "Eric Brewer, 'CAP Theorem' (PODC 2000) | "
    "Martin Kleppmann, 'Designing Data-Intensive Applications' (O'Reilly, 2017) | "
    "Michael Nygard, 'Release It! 2nd Ed.' (Pragmatic, 2018) | "
    "Google SRE Book, 'Site Reliability Engineering' (O'Reilly, 2016)"
)


class SystemDesignAdvisorTool(BaseTool):
    """시스템 설계 자문 도구 — CAP 정리 기반 교수급 아키텍처 설계 자문.

    분산 시스템의 확장성, 저장소 선택, 통신 패턴, 신뢰성, 보안, 관측성을
    학술 근거(Brewer 2000, Kleppmann 2017, Nygard 2018, Google SRE 2016)에 기반하여
    종합적으로 분석하고 실무 적용 가능한 권고안을 제시합니다.
    """

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "design")
        actions = {
            "design": self._design_advisory,
            "scalability": self._scalability_analysis,
            "datastore": self._datastore_selection,
            "communication": self._communication_analysis,
            "reliability": self._reliability_design,
            "security": self._security_architecture,
            "observability": self._observability_design,
            "full": self._full_analysis,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return (
            f"알 수 없는 action: {action}. "
            "design, scalability, datastore, communication, reliability, "
            "security, observability, full 중 하나를 사용하세요."
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. design — 시스템 설계 종합 자문 (CAP 정리 기반)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _design_advisory(self, p: dict) -> str:
        system_name = p.get("system_name", "대상 시스템")
        requirements = p.get("requirements", "")
        expected_qps = p.get("expected_qps", "")
        data_size = p.get("data_size", "")
        consistency_need = p.get("consistency", "eventual")

        if not requirements:
            return self._design_guide()

        # CAP 분석 테이블
        lines = [
            f"# 시스템 설계 자문 보고서: {system_name}",
            "",
            "## CAP 정리 기반 분석 (Eric Brewer, 2000)",
            "",
            "| CAP 요소 | 설명 | 해당 시스템 적용 |",
            "|----------|------|----------------|",
        ]
        for key in ("Consistency", "Availability", "Partition_Tolerance"):
            cap = _CAP_THEOREM[key]
            lines.append(f"| {key} | {cap['desc']} | {cap['use_case']} |")

        lines.extend([
            "",
            "### CAP 조합별 적합 시스템",
            "| 조합 | 설명 | 대표 DB | 적합 시나리오 |",
            "|------|------|--------|-------------|",
        ])
        for combo in ("CP_Systems", "AP_Systems", "CA_Systems"):
            c = _CAP_THEOREM[combo]
            lines.append(f"| {combo.replace('_', ' ')} | {c['desc']} | {c['examples']} | {c['when']} |")

        # LLM 기반 맞춤 자문
        system_prompt = (
            "당신은 분산 시스템 설계 교수이자 Google/Meta 수석 아키텍트 출신 자문가입니다. "
            "CAP 정리(Brewer, 2000), Kleppmann(2017), Nygard(2018)의 학술 근거를 기반으로 "
            "구체적이고 실무 적용 가능한 아키텍처를 제안하세요. "
            "반드시 한국어 마크다운으로 작성하세요."
        )
        user_prompt = (
            f"시스템: {system_name}\n"
            f"요구사항: {requirements}\n"
            f"예상 QPS: {expected_qps}\n"
            f"데이터 규모: {data_size}\n"
            f"일관성 요구: {consistency_need}\n\n"
            "다음을 포함하여 아키텍처를 제안해주세요:\n"
            "1. CAP 선택 근거 (CP/AP/CA 중 어떤 조합이 적합한지)\n"
            "2. 추천 아키텍처 다이어그램 (텍스트 기반)\n"
            "3. 핵심 컴포넌트 목록과 기술 스택\n"
            "4. 예상 병목 지점과 해결 전략\n"
            "5. 단계별 구축 로드맵 (MVP → Scale)"
        )
        llm_advice = await self._llm_call(system_prompt, user_prompt)

        lines.extend([
            "",
            "---",
            "## 맞춤 아키텍처 자문",
            "",
            llm_advice,
            "",
            "---",
            f"*학술 참고: {_REFERENCES}*",
        ])
        return "\n".join(lines)

    def _design_guide(self) -> str:
        return "\n".join([
            "### 시스템 설계 자문을 위해 필요한 입력값:",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            "| system_name | 설계 대상 시스템 이름 | 실시간 채팅 플랫폼 |",
            "| requirements | 핵심 요구사항 (쉼표 구분) | 실시간 메시지, 읽음 확인, 그룹채팅 |",
            "| expected_qps | 예상 초당 요청 수 | 10,000 QPS |",
            "| data_size | 예상 데이터 규모 | 일 1억 메시지, 총 10TB |",
            "| consistency | 일관성 요구 수준 | strong, eventual, causal |",
        ])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. scalability — 확장성 패턴 분석
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _scalability_analysis(self, p: dict) -> str:
        system_name = p.get("system_name", "대상 시스템")
        current_load = p.get("current_load", "")
        target_load = p.get("target_load", "")
        bottleneck = p.get("bottleneck", "")

        lines = [
            f"# 확장성 패턴 분석: {system_name}",
            "",
            "## 5가지 핵심 확장 전략 (Kleppmann, 2017)",
            "",
            "| 패턴 | 설명 | 장점 | 단점 | 적합 대상 |",
            "|------|------|------|------|----------|",
        ]
        for key, pat in _SCALABILITY_PATTERNS.items():
            lines.append(
                f"| {pat['name']} | {pat['desc']} | {pat['pros']} | {pat['cons']} | {pat['best_for']} |"
            )

        lines.extend([
            "",
            "### 패턴별 도구/기술 스택",
            "| 패턴 | 주요 도구 |",
            "|------|----------|",
        ])
        for key, pat in _SCALABILITY_PATTERNS.items():
            lines.append(f"| {pat['name']} | {pat['tools']} |")

        if current_load or target_load or bottleneck:
            system_prompt = (
                "당신은 대규모 트래픽 시스템 설계 전문가입니다. "
                "Kleppmann(2017)과 Google SRE(2016)의 확장 전략을 기반으로 "
                "구체적인 확장 계획을 한국어 마크다운으로 제안하세요."
            )
            user_prompt = (
                f"시스템: {system_name}\n"
                f"현재 부하: {current_load}\n"
                f"목표 부하: {target_load}\n"
                f"병목 지점: {bottleneck}\n\n"
                "단계별 확장 전략과 예상 비용, 구현 우선순위를 제안해주세요."
            )
            llm_advice = await self._llm_call(system_prompt, user_prompt)
            lines.extend(["", "---", "## 맞춤 확장 전략", "", llm_advice])

        lines.extend(["", "---", f"*학술 참고: {_REFERENCES}*"])
        return "\n".join(lines)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. datastore — 데이터 저장소 선택 자문
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _datastore_selection(self, p: dict) -> str:
        use_case = p.get("use_case", "")
        data_model = p.get("data_model", "")
        read_write_ratio = p.get("read_write_ratio", "")
        scale_requirement = p.get("scale_requirement", "")

        lines = [
            "# 데이터 저장소 선택 가이드",
            "",
            "## 6가지 데이터 저장소 비교 (Kleppmann, 2017)",
            "",
            "| 유형 | 대표 제품 | 강점 | 약점 | CAP | 적합 대상 |",
            "|------|----------|------|------|-----|----------|",
        ]
        for key, ds in _DATA_STORES.items():
            lines.append(
                f"| {ds['name']} | {ds['examples']} | {ds['strengths']} | "
                f"{ds['weaknesses']} | {ds['cap']} | {ds['best_for']} |"
            )

        lines.extend([
            "",
            "### 확장 전략별 비교",
            "| 유형 | 확장 방식 |",
            "|------|----------|",
        ])
        for key, ds in _DATA_STORES.items():
            lines.append(f"| {ds['name']} | {ds['scale']} |")

        if use_case or data_model:
            system_prompt = (
                "당신은 데이터베이스 아키텍트이자 Kleppmann 'DDIA'(2017) 전문가입니다. "
                "사용 사례에 맞는 최적 데이터 저장소를 한국어 마크다운으로 추천하세요. "
                "반드시 근거와 대안, 마이그레이션 전략도 포함하세요."
            )
            user_prompt = (
                f"사용 사례: {use_case}\n"
                f"데이터 모델: {data_model}\n"
                f"읽기/쓰기 비율: {read_write_ratio}\n"
                f"확장 요구: {scale_requirement}\n\n"
                "1순위 추천 저장소와 근거, 2순위 대안, "
                "그리고 향후 마이그레이션 시나리오를 제안해주세요."
            )
            llm_advice = await self._llm_call(system_prompt, user_prompt)
            lines.extend(["", "---", "## 맞춤 저장소 추천", "", llm_advice])

        lines.extend(["", "---", f"*학술 참고: {_REFERENCES}*"])
        return "\n".join(lines)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4. communication — 통신 패턴 비교 분석
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _communication_analysis(self, p: dict) -> str:
        system_name = p.get("system_name", "대상 시스템")
        service_count = p.get("service_count", "")
        latency_requirement = p.get("latency_requirement", "")
        communication_type = p.get("communication_type", "")

        lines = [
            f"# 통신 패턴 분석: {system_name}",
            "",
            "## 5가지 통신 패턴 비교",
            "",
            "| 패턴 | 프로토콜 | 포맷 | 지연 시간 | 강점 | 약점 | 적합 대상 |",
            "|------|---------|------|---------|------|------|----------|",
        ]
        for key, cp in _COMMUNICATION_PATTERNS.items():
            lines.append(
                f"| {cp['name']} | {cp['protocol']} | {cp['format']} | "
                f"{cp['latency']} | {cp['strengths']} | {cp['weaknesses']} | {cp['best_for']} |"
            )

        if service_count or latency_requirement or communication_type:
            system_prompt = (
                "당신은 분산 시스템 통신 전문가입니다. "
                "서비스 간 통신 패턴을 분석하고 최적의 조합을 한국어 마크다운으로 제안하세요. "
                "실제 사례와 함께 구체적인 구현 권고를 포함하세요."
            )
            user_prompt = (
                f"시스템: {system_name}\n"
                f"서비스 수: {service_count}\n"
                f"지연 요구사항: {latency_requirement}\n"
                f"통신 유형: {communication_type}\n\n"
                "서비스 간 통신 전략을 추천하되, "
                "동기/비동기 분리, API 게이트웨이 필요성, "
                "이벤트 기반 아키텍처 적용 여부를 포함해주세요."
            )
            llm_advice = await self._llm_call(system_prompt, user_prompt)
            lines.extend(["", "---", "## 맞춤 통신 전략", "", llm_advice])

        lines.extend(["", "---", f"*학술 참고: {_REFERENCES}*"])
        return "\n".join(lines)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 5. reliability — 신뢰성 설계 자문
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _reliability_design(self, p: dict) -> str:
        system_name = p.get("system_name", "대상 시스템")
        sla_target = p.get("sla_target", "99.9%")
        failure_scenarios = p.get("failure_scenarios", "")
        current_architecture = p.get("current_architecture", "")

        # SLA → 허용 다운타임 계산
        sla_downtime = {
            "99%": "연 3.65일 / 월 7.31시간",
            "99.9%": "연 8.77시간 / 월 43.83분",
            "99.95%": "연 4.38시간 / 월 21.92분",
            "99.99%": "연 52.60분 / 월 4.38분",
            "99.999%": "연 5.26분 / 월 26.30초",
        }

        lines = [
            f"# 신뢰성 설계 자문: {system_name}",
            "",
            "## SLA별 허용 다운타임 (Google SRE, 2016)",
            "",
            "| SLA 목표 | 허용 다운타임 |",
            "|---------|-------------|",
        ]
        for sla, downtime in sla_downtime.items():
            marker = " <-- 현재 목표" if sla == sla_target else ""
            lines.append(f"| {sla} | {downtime}{marker} |")

        lines.extend([
            "",
            "## 4가지 장애 복원 패턴 (Nygard, 'Release It!' 2018)",
            "",
        ])
        for key, rp in _RELIABILITY_PATTERNS.items():
            lines.extend([
                f"### {rp['name']}",
                f"- **설명**: {rp['desc']}",
            ])
            if "states" in rp:
                lines.append(f"- **상태 전이**: {rp['states']}")
            if "types" in rp:
                lines.append(f"- **유형**: {rp['types']}")
            if "formula" in rp:
                lines.append(f"- **공식**: `{rp['formula']}`")
            if "metrics" in rp:
                lines.append(f"- **핵심 지표**: {rp['metrics']}")
            lines.extend([
                f"- **설정**: {rp['config']}",
                f"- **도구**: {rp['tools']}",
                f"- **예시**: {rp['example']}",
                "",
            ])

        if failure_scenarios or current_architecture:
            system_prompt = (
                "당신은 장애 복원 설계 전문가이자 SRE 리더입니다. "
                "Nygard(2018)와 Google SRE(2016)의 패턴을 기반으로 "
                "구체적인 장애 대응 아키텍처를 한국어 마크다운으로 제안하세요."
            )
            user_prompt = (
                f"시스템: {system_name}\n"
                f"SLA 목표: {sla_target}\n"
                f"장애 시나리오: {failure_scenarios}\n"
                f"현재 아키텍처: {current_architecture}\n\n"
                "다음을 포함하여 신뢰성 설계를 제안해주세요:\n"
                "1. 장애 시나리오별 대응 패턴 매핑\n"
                "2. Circuit Breaker + Retry + Bulkhead 조합 전략\n"
                "3. Failover 아키텍처 (Active-Passive vs Active-Active)\n"
                "4. Chaos Engineering 테스트 계획\n"
                "5. SLA 달성을 위한 에러 버짓(Error Budget) 정책"
            )
            llm_advice = await self._llm_call(system_prompt, user_prompt)
            lines.extend(["---", "## 맞춤 신뢰성 설계", "", llm_advice])

        lines.extend(["", "---", f"*학술 참고: {_REFERENCES}*"])
        return "\n".join(lines)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 6. security — 보안 아키텍처 자문
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _security_architecture(self, p: dict) -> str:
        system_name = p.get("system_name", "대상 시스템")
        data_sensitivity = p.get("data_sensitivity", "중간")
        compliance = p.get("compliance", "")
        auth_requirements = p.get("auth_requirements", "")

        security_layers = {
            "Zero Trust": {
                "principle": "절대 신뢰하지 않고, 항상 검증 (Never Trust, Always Verify)",
                "components": "Identity Verification, Device Trust, Network Segmentation, Least Privilege",
                "tools": "BeyondCorp (Google), Zscaler, Okta, Cloudflare Access",
            },
            "OAuth2 + OIDC": {
                "principle": "위임된 인가 + 신원 확인 (Authorization + Authentication)",
                "components": "Authorization Server, Resource Server, Access/Refresh Token, PKCE",
                "tools": "Keycloak, Auth0, AWS Cognito, Firebase Auth",
            },
            "mTLS": {
                "principle": "상호 TLS — 클라이언트와 서버 모두 인증서로 신원 확인",
                "components": "CA (Certificate Authority), 인증서 발급/갱신, 인증서 폐기 목록 (CRL)",
                "tools": "Istio, Linkerd, SPIFFE/SPIRE, Cert-Manager",
            },
            "Secret Management": {
                "principle": "비밀 정보(API 키, DB 암호 등)의 중앙 집중 관리 + 자동 로테이션",
                "components": "Vault, Secret Rotation, Dynamic Secrets, Encryption as a Service",
                "tools": "HashiCorp Vault, AWS Secrets Manager, GCP Secret Manager, SOPS",
            },
        }

        lines = [
            f"# 보안 아키텍처 자문: {system_name}",
            "",
            "## 4계층 보안 프레임워크",
            "",
        ]
        for layer_name, layer in security_layers.items():
            lines.extend([
                f"### {layer_name}",
                f"- **원칙**: {layer['principle']}",
                f"- **구성 요소**: {layer['components']}",
                f"- **도구**: {layer['tools']}",
                "",
            ])

        lines.extend([
            "## 데이터 민감도별 보안 수준",
            "",
            "| 민감도 | 암호화 | 접근 제어 | 감사 로그 | 규제 예시 |",
            "|--------|--------|----------|----------|----------|",
            "| 낮음 | 전송 중 (TLS) | RBAC | 기본 로그 | - |",
            "| 중간 | 전송 중 + 저장 시 (AES-256) | RBAC + MFA | 상세 감사 | ISMS |",
            "| 높음 | E2E + 저장 시 + 필드 레벨 | ABAC + MFA + IP 제한 | 실시간 SIEM | GDPR, PCI-DSS |",
            "| 최고 | HSM 기반 키 관리 + 동형 암호 | Zero Trust + 생체 인증 | 실시간 + 블록체인 | 금융감독원, HIPAA |",
        ])

        if data_sensitivity or compliance or auth_requirements:
            system_prompt = (
                "당신은 사이버 보안 아키텍트이자 CISSP/CISM 보유 전문가입니다. "
                "Zero Trust 원칙에 기반하여 실무에 즉시 적용 가능한 "
                "보안 아키텍처를 한국어 마크다운으로 제안하세요."
            )
            user_prompt = (
                f"시스템: {system_name}\n"
                f"데이터 민감도: {data_sensitivity}\n"
                f"규제 준수: {compliance}\n"
                f"인증 요구사항: {auth_requirements}\n\n"
                "다음을 포함하여 보안 아키텍처를 제안해주세요:\n"
                "1. 인증/인가 아키텍처 (OAuth2 + RBAC/ABAC)\n"
                "2. 네트워크 보안 (mTLS, WAF, DDoS 방어)\n"
                "3. 데이터 보안 (암호화, 마스킹, 토큰화)\n"
                "4. 비밀 관리 (Vault 기반 키 로테이션)\n"
                "5. 위협 모델링 (STRIDE) 및 대응 전략"
            )
            llm_advice = await self._llm_call(system_prompt, user_prompt)
            lines.extend(["", "---", "## 맞춤 보안 설계", "", llm_advice])

        lines.extend(["", "---", f"*학술 참고: {_REFERENCES}*"])
        return "\n".join(lines)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 7. observability — 관측성 설계 자문
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _observability_design(self, p: dict) -> str:
        system_name = p.get("system_name", "대상 시스템")
        current_monitoring = p.get("current_monitoring", "")
        alert_requirements = p.get("alert_requirements", "")

        # 관측성 3대 축 (Google SRE, 2016)
        three_pillars = {
            "Metrics (메트릭)": {
                "desc": "수치화된 시계열 측정값 — 시스템의 '건강 상태'를 보여줌",
                "types": "Counter (누적), Gauge (현재값), Histogram (분포), Summary (백분위)",
                "golden_signals": "지연 시간(Latency), 트래픽(Traffic), 오류율(Errors), 포화도(Saturation)",
                "tools": "Prometheus + Grafana, Datadog, CloudWatch, New Relic",
                "example": "HTTP 요청 지연 p99 < 200ms, 오류율 < 0.1%, CPU 사용률 < 70%",
            },
            "Logs (로그)": {
                "desc": "개별 이벤트의 구조화된 기록 — '무엇이 일어났는지'를 설명",
                "types": "구조화 로그(JSON), 반구조화(Syslog), 비구조화(텍스트)",
                "best_practices": "구조화 JSON, 상관관계 ID(Correlation ID), 로그 레벨 표준화, 샘플링",
                "tools": "ELK Stack (Elasticsearch + Logstash + Kibana), Loki + Grafana, Fluentd, Splunk",
                "example": "{\"timestamp\":\"...\", \"level\":\"ERROR\", \"trace_id\":\"abc123\", \"msg\":\"DB timeout\"}",
            },
            "Traces (트레이스)": {
                "desc": "요청의 전체 여정 추적 — 서비스 간 '인과관계'를 보여줌",
                "types": "분산 트레이스(Span 트리), 프로파일링, 서비스 맵",
                "standards": "OpenTelemetry (OTLP), W3C Trace Context, Baggage",
                "tools": "Jaeger, Zipkin, Tempo (Grafana), AWS X-Ray, Honeycomb",
                "example": "API Gateway → Auth Service (5ms) → Order Service (12ms) → DB (45ms) = 총 62ms",
            },
        }

        lines = [
            f"# 관측성 설계 자문: {system_name}",
            "",
            "## 관측성 3대 축 (Google SRE Book, 2016)",
            "",
        ]
        for pillar_name, pillar in three_pillars.items():
            lines.extend([
                f"### {pillar_name}",
                f"- **정의**: {pillar['desc']}",
                f"- **유형**: {pillar['types']}",
            ])
            if "golden_signals" in pillar:
                lines.append(f"- **4대 골든 시그널**: {pillar['golden_signals']}")
            if "best_practices" in pillar:
                lines.append(f"- **모범 사례**: {pillar['best_practices']}")
            if "standards" in pillar:
                lines.append(f"- **표준**: {pillar['standards']}")
            lines.extend([
                f"- **도구**: {pillar['tools']}",
                f"- **예시**: `{pillar['example']}`",
                "",
            ])

        lines.extend([
            "## SLI/SLO/SLA 프레임워크 (Google SRE, 2016)",
            "",
            "| 개념 | 정의 | 예시 |",
            "|------|------|------|",
            "| SLI (Service Level Indicator) | 측정 가능한 서비스 품질 지표 | p99 지연 시간, 가용률 |",
            "| SLO (Service Level Objective) | SLI의 목표 범위 | p99 < 200ms, 가용률 > 99.9% |",
            "| SLA (Service Level Agreement) | SLO 미달 시 보상 계약 | 가용률 99.9% 미달 시 10% 크레딧 |",
            "| Error Budget (에러 버짓) | 허용 가능한 오류 총량 | 월 43.83분 다운타임 허용 |",
        ])

        if current_monitoring or alert_requirements:
            system_prompt = (
                "당신은 관측성(Observability) 전문가이자 Google SRE 출신입니다. "
                "Metrics, Logs, Traces 3대 축과 SLI/SLO 프레임워크를 기반으로 "
                "실무에 즉시 적용 가능한 관측성 설계를 한국어 마크다운으로 제안하세요."
            )
            user_prompt = (
                f"시스템: {system_name}\n"
                f"현재 모니터링: {current_monitoring}\n"
                f"알림 요구사항: {alert_requirements}\n\n"
                "다음을 포함하여 관측성 아키텍처를 제안해주세요:\n"
                "1. Metrics: 수집 대상 메트릭 + 4대 골든 시그널 대시보드 설계\n"
                "2. Logs: 구조화 로그 표준 + 중앙 집중 수집 파이프라인\n"
                "3. Traces: 분산 트레이싱 도입 전략 (OpenTelemetry)\n"
                "4. Alerting: 알림 체계 (PagerDuty 연동, 에스컬레이션)\n"
                "5. SLO 대시보드 + 에러 버짓 정책"
            )
            llm_advice = await self._llm_call(system_prompt, user_prompt)
            lines.extend(["", "---", "## 맞춤 관측성 설계", "", llm_advice])

        lines.extend(["", "---", f"*학술 참고: {_REFERENCES}*"])
        return "\n".join(lines)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 8. full — 전체 종합 (asyncio.gather 병렬)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _full_analysis(self, p: dict) -> str:
        system_name = p.get("system_name", "대상 시스템")

        if not p.get("requirements"):
            return self._full_guide()

        # 7개 분석을 asyncio.gather로 병렬 실행
        results = await asyncio.gather(
            self._design_advisory(p),
            self._scalability_analysis(p),
            self._datastore_selection(p),
            self._communication_analysis(p),
            self._reliability_design(p),
            self._security_architecture(p),
            self._observability_design(p),
        )

        section_titles = [
            "Part 1: 시스템 설계 종합 자문 (CAP 정리 기반)",
            "Part 2: 확장성 패턴 분석",
            "Part 3: 데이터 저장소 선택",
            "Part 4: 통신 패턴 분석",
            "Part 5: 신뢰성 설계",
            "Part 6: 보안 아키텍처",
            "Part 7: 관측성 설계",
        ]

        lines = [
            f"# 시스템 설계 종합 보고서: {system_name}",
            "",
            "> 7개 영역 병렬 분석 완료 (asyncio.gather)",
            "",
            "---",
        ]

        for title, content in zip(section_titles, results):
            lines.extend([
                "",
                f"## {title}",
                "",
                content,
                "",
                "---",
            ])

        lines.extend([
            "",
            "## 종합 참고 문헌",
            "",
            "| 저자 | 제목 | 출판 | 핵심 기여 |",
            "|------|------|------|----------|",
            "| Eric Brewer | CAP Theorem | PODC 2000 | 분산 시스템 트레이드오프 정의 |",
            "| Martin Kleppmann | Designing Data-Intensive Applications | O'Reilly 2017 | 데이터 중심 설계 바이블 |",
            "| Michael Nygard | Release It! 2nd Ed. | Pragmatic 2018 | 프로덕션 안정성 패턴 |",
            "| Google SRE Team | Site Reliability Engineering | O'Reilly 2016 | SLO/관측성 프레임워크 |",
        ])
        return "\n".join(lines)

    def _full_guide(self) -> str:
        return "\n".join([
            "### 전체 종합 분석을 위해 필요한 입력값:",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            "| system_name | 시스템 이름 | 실시간 채팅 플랫폼 |",
            "| requirements | 핵심 요구사항 | 실시간 메시지, 읽음 확인, 검색 |",
            "| expected_qps | 예상 QPS | 10,000 |",
            "| data_size | 데이터 규모 | 일 1억 건, 총 10TB |",
            "| consistency | 일관성 요구 | strong, eventual, causal |",
            "| sla_target | SLA 목표 | 99.9%, 99.99% |",
            "| data_sensitivity | 데이터 민감도 | 낮음, 중간, 높음, 최고 |",
            "",
            "모든 7개 영역(설계/확장/저장소/통신/신뢰성/보안/관측성)을",
            "asyncio.gather로 병렬 분석하여 종합 보고서를 생성합니다.",
            "",
            f"*학술 참고: {_REFERENCES}*",
        ])
