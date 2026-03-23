# Vega 코드베이스 품질 평가 보고서

> **평가 기준 빌드**: PR#5 (`19c2fc6` — Merge pull request #5: refactor 모놀리식 모듈을 패키지 구조로 분리)
> **평가 일자**: 2026-03-23

---

## 종합 점수: 2.8 / 5.0

| 평가 항목 | 점수 | 비고 |
|---|:---:|---|
| 1. 코드 품질 & 유지보수성 | **3.0** | snake_case 준수, bare except 없음. God module, 타입 힌트 부족 |
| 2. 아키텍처 & 설계 | **3.5** | 커맨드 레지스트리, 애드온 시스템, 하이브리드 검색. core.py 과부하 |
| 3. 테스팅 & 신뢰성 | **2.0** | 테스트 2개/55 소스, CI/CD 없음 |
| 4. 문서화 & 개발자 경험 | **2.5** | CLAUDE.md 존재. README 없음, docstring 부족 |
| 5. 보안 | **3.0** | 파라미터화 쿼리 사용. 동적 컬럼명 위험, 의존성 관리 없음 |
| 6. 성능 & 확장성 | **3.5** | WAL 모드, FTS5 인덱스, 증분 업데이트. 동기 I/O만 사용 |
| 7. DevOps & 도구 | **1.5** | 운영 스크립트 존재. CI/CD·린터·패키징 전무 |
| 8. 기술 부채 | **3.0** | TODO 10건. 레거시 파일 4개, 스텁 존재 |

**가중치**: 아키텍처(20%), 테스팅(15%), 보안(15%), 코드품질(15%), 성능(10%), 문서화(10%), DevOps(10%), 기술부채(5%)

---

## 기본 지표

| 지표 | 값 |
|---|---|
| 총 코드량 | ~13,500 LOC (Python) |
| 소스 파일 | 55개 |
| 테스트 파일 | 2개 (~1,100 LOC) |
| 테스트-소스 비율 | 0.036 |
| 300줄 초과 파일 | 7개 |
| 타입 힌트 적용률 | 13.6% (24/177 함수에 반환 타입) |
| TODO/FIXME/HACK | 10건 |
| 패키징 (pyproject.toml/requirements.txt) | 없음 |
| CI/CD | 없음 |
| 린터/포매터 | 없음 |

---

## 1. 코드 품질 & 유지보수성 — 3.0/5

### 강점
- **PEP 8 네이밍** 준수 — snake_case 일관 적용
- **bare `except:` 없음** — 모든 85개 except 절이 예외 타입 지정
- 커맨드/애드온 분리가 깔끔 (`commands/`, `addons/`)
- PR#5에서 모놀리식 `project_db_v2.py`를 `db/` 패키지로 분리 완료

### 약점
- **God module 패턴**
  - `core.py` (1,287줄) — 라우팅, 세션, 실행 엔진, 에러 처리, NL 매칭 혼재
  - `search/router.py` (1,090줄) — FTS5, 시맨틱, 하이브리드, 프로젝트 추론 등 다수 책임
- **타입 힌트 13.6%** — 177개 함수 중 24개만 반환 타입 어노테이션
- **린터/포매터 미설정** — 코드 스타일 일관성이 개인 습관에 의존

### 권고
- `core.py` 분리: `routing.py` (NL 라우팅), `session.py` (세션 관리), `executor.py` (커맨드 실행)
- ruff 도입 (lint + format 통합, Python 생태계 최적)
- 공개 함수에 최소한 반환 타입 힌트 추가

---

## 2. 아키텍처 & 설계 — 3.5/5

### 강점
- **커맨드 레지스트리 패턴** — `@register_command` 데코레이터 기반 자동 등록, `commands/` 디렉토리 자동 스캔
- **애드온 시스템** — `BaseAddon` 추상 클래스, `run()`/`api()` 이중 인터페이스
- **하이브리드 검색 파이프라인** — FTS5 (어휘) + 벡터 (의미) + 리랭킹 (Qwen3) 3단계
- **구조화된 JSON 응답** — `{command, status, data, summary, _performance, _meta, _ai_hint, _bundle}` 엔벨로프
- **세션 관리** — 30분 TTL, 대명사 해석 ("그 프로젝트" → 최근 프로젝트)
- **MCP 프로토콜 준수** — Deneb/OpenClaw 통합

### 약점
- `core.py`에 5가지 이상 책임 혼재 (SRP 위반)
- DB 접근이 `config.get_db_connection()` 중앙화되었으나, 일부 커맨드에서 직접 SQL 조합
- 레이어 간 명확한 의존 방향 미정의 (commands → core → db 순환 가능)

### 권고
- `core.py`를 단일 책임 모듈로 분리
- DB 접근을 repository 패턴으로 통일 (커맨드에서 직접 SQL 제거)

---

## 3. 테스팅 & 신뢰성 — 2.0/5

### 강점
- `test_vega.py` (~1,100줄) — 주요 커맨드 (ask, search, brief, show, update, urgent) 커버
- `VegaTestCase` 베이스 클래스 — 픽스처 .md 자동 생성, 인메모리 DB, 헬퍼 메서드
- `_test_search_quality.py` — 검색 품질 벤치마킹 (비공식)

### 약점
- **테스트 파일 2개 / 소스 55개** — 비율 3.6%
- **CI/CD 없음** — 테스트 자동 실행 미보장, 회귀 방지 불가
- **테스트 부재 모듈**:
  - `ml/` (embedder, reranker, expander, search, manager) — 0 테스트
  - `search/router.py` (1,090줄) — 0 테스트
  - `mail/converter.py` (606줄) — 0 테스트
  - `editor/md.py` — 0 테스트
  - `addons/` (8개 애드온) — 0 테스트
- **통합/E2E 테스트 없음**

### 권고
- **Critical**: GitHub Actions CI 파이프라인 구축 (`python -m unittest discover`)
- `search/router.py`, `ml/`, `editor/` 단위 테스트 추가
- 애드온 테스트 기본 구조 마련

---

## 4. 문서화 & 개발자 경험 — 2.5/5

### 강점
- **CLAUDE.md** (440줄) — MCP 도구 레퍼런스, 응답 구조, 에러 복구, 개발 가이드
- **CHANGELOG.md** — v1.44 → v1.49 상세 버전 히스토리

### 약점
- **README 없음** — 프로젝트 발견성, 목적, 설치 방법, 빠른 시작 가이드 부재
- **Python docstring 거의 없음** — 177개 함수 중 대부분 문서 미작성
- 설치/설정 가이드가 `setup.sh`, `install.sh` 셸 스크립트에만 존재 — 가독성 낮음
- 아키텍처 다이어그램 없음

### 권고
- README.md 작성 (목적, 설치, 빠른 시작, 아키텍처 개요)
- 공개 함수에 docstring 추가 (최소 커맨드 핸들러, 애드온 API)

---

## 5. 보안 — 3.0/5

### 강점
- **파라미터화 쿼리 사용** — f-string SQL 3건 확인, 모두 값은 `?` 플레이스홀더 사용
  - `editor/md.py:161` — `f"UPDATE projects SET {db_field} = ?"` (컬럼명만 동적)
  - `commands/write.py:225` — `f"DELETE FROM chunk_tags WHERE chunk_id IN ({','.join('?' * len(old_ids))})"` (플레이스홀더)
  - `commands/write.py:234` — 동일 패턴
- **bare `except:` 없음** — 예외 누락 방지
- **구조화된 에러 응답** — `VegaError`에 `error_type`, `recovery`, `did_you_mean` 포함

### 약점
- `editor/md.py:161`의 `{db_field}` — 사용자 입력에서 유래할 경우 SQL 인젝션 가능
- **의존성 관리 없음** — requirements.txt/pyproject.toml 부재로 버전 고정 불가
- **의존성 보안 스캐닝 없음**
- 인증/인가 메커니즘 없음 (MCP 서버 모드에서의 접근 제어)

### 권고
- `db_field`에 허용 컬럼 화이트리스트 검증 추가
- `pyproject.toml` + `pip-audit` 또는 `safety` 도입
- MCP 서버 접근 제어 검토

---

## 6. 성능 & 확장성 — 3.5/5

### 강점
- **SQLite WAL 모드** + `busy_timeout` — 안전한 동시 접근
- **파일 해시 기반 증분 업데이트** — 변경된 .md만 DB 반영 (`db/importer.py`)
- **FTS5 인덱스** — 프로젝트명, 클라이언트, 섹션, 내용에 대한 빠른 전문 검색
- **GGUF 로컬 추론** — 외부 API 의존 제거, 프라이버시 보장
- **`_performance` 메타데이터** — 응답마다 `elapsed_ms` 포함

### 약점
- **동기 I/O만 사용** — MCP 서버 모드에서 동시 요청 처리 시 병목
- **모델 로딩 전략 불명확** — GGUF 모델 메모리 상주 vs 요청별 로드
- **쿼리 결과 캐싱 없음**

### 권고
- MCP 서버 모드에 대한 동시성 프로파일링
- 자주 사용되는 검색 쿼리 결과 캐싱 고려
- 모델 라이프사이클 문서화 (로드/언로드 시점, 메모리 사용량)

---

## 7. DevOps & 도구 — 1.5/5

### 강점
- 운영 스크립트 존재: `bootstrap.sh` (세션 시작), `sync-db.sh` (파일 감시 데몬), `setup.sh`/`install.sh`
- MCP 서버 설정 (`mcp-vega.json`)
- `vega-wrapper.sh` — MCP bash 래퍼

### 약점
- **CI/CD 완전 부재** — GitHub Actions, GitLab CI 등 없음
- **린터/포매터 미설정** — ruff, flake8, black, isort 등 없음
- **패키징 없음** — `pyproject.toml`, `setup.py`, `requirements.txt` 모두 없음
- **재현 가능한 빌드 불가** — 의존성 버전 고정 수단 없음
- **pre-commit hooks 없음**
- **테스트 자동화 없음** — `python3 -m unittest` 수동 실행에 의존

### 권고
1. `pyproject.toml` 작성 (프로젝트 메타데이터 + 의존성)
2. ruff 도입 (`.ruff.toml` 설정)
3. GitHub Actions CI 구축 (lint → test → type-check)
4. pre-commit hooks 설정

---

## 8. 기술 부채 — 3.0/5

### 강점
- **TODO/FIXME 10건** — 13.5K LOC 대비 적은 편 (0.07%)
- **CHANGELOG 기반 버전 관리** — v1.44 → v1.49 추적
- PR#5에서 모놀리식 DB 모듈을 패키지로 리팩토링 완료

### 약점
- **레거시 파일 4개**:
  - `project_db_v2.py` — 하위 호환 래퍼 (db/ 패키지로 이전 완료)
  - `router.py` (루트) — 대부분의 로직이 core.py로 이동됨
  - `models.py` — 스텁 파일 (내용 없음)
  - `md_editor.py` — `editor/md.py`와 중복 가능성
- **Python 3.10+ 기능 미활용** — match/case, 타입 유니온(`X | Y`), `TypeAlias` 등

### 권고
- 레거시 파일 4개 제거 (의존성 확인 후)
- Python 3.10+ 패턴 매칭으로 NL 라우팅 리팩토링 고려

---

## Top 3 강점

1. **잘 설계된 하이브리드 검색 아키텍처** — FTS5 + 벡터 임베딩 + 리랭킹의 3단계 파이프라인으로, 어휘적·의미적 검색을 모두 지원하는 성숙한 검색 엔진
2. **AI 에이전트 친화적 응답 설계** — 구조화된 JSON 엔벨로프, `_ai_hint`, `_meta`, `_bundle` 등 AI가 다음 행동을 결정할 수 있는 메타데이터 설계
3. **확장 가능한 커맨드/애드온 시스템** — 데코레이터 기반 자동 등록, BaseAddon 추상 클래스, 커맨드 추가 시 core 수정 불필요

## Top 3 약점

1. **CI/CD·린터·패키징 전무** — 코드 품질 자동 보장 수단이 없으며, 재현 가능한 빌드가 불가능
2. **테스트 커버리지 극히 낮음** — 55개 소스 파일 중 2개만 테스트, 검색 엔진·ML 모듈·에디터·애드온이 완전 미테스트
3. **God module 패턴** — `core.py`(1,287줄)와 `search/router.py`(1,090줄)에 과도한 책임 집중

---

## 개선 우선순위

| 순위 | 권고사항 | 노력 | 영향 |
|:---:|---------|:---:|------|
| 1 | CI/CD 파이프라인 구축 (GitHub Actions) | M | 테스팅, DevOps |
| 2 | `pyproject.toml` + 의존성 고정 | S | DevOps, 보안 |
| 3 | ruff 린터 도입 | S | 코드품질, DevOps |
| 4 | `core.py` 분리 (라우팅/세션/실행) | M | 아키텍처, 유지보수 |
| 5 | 주요 모듈 테스트 추가 (`search/router.py`, `ml/`, `editor/`) | L | 테스팅 |
| 6 | README.md 작성 | S | 문서화 |
| 7 | 타입 힌트 확대 (공개 함수 반환 타입) | M | 코드품질 |
| 8 | `editor/md.py:161` 동적 컬럼명 화이트리스트 | S | 보안 |
| 9 | 레거시 파일 정리 (4개) | S | 기술부채 |
