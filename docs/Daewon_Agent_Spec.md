# 대원제약 제제연구 AI 에이전트 개발 명세서 (Gemini Enterprise 기반)

본 문서는 대원제약 중앙연구소 제제연구팀의 '시험 처방 설계 및 검증 자동화' 시나리오(PoC101)를 바탕으로, Google Gemini Enterprise Agent Platform 환경에서 구현할 AI 에이전트의 설계 및 개발 명세를 정의합니다.

## 1. 개요 및 워크플로우

본 에이전트는 물성 데이터와 제조처 DMF 자료를 기반으로 최적의 시험 처방 3종을 자동 제안하고, 실험 결과의 편차를 분석하여 개선안을 생성하는 End-to-End 자동화 파이프라인을 구축하는 것을 목표로 합니다. 전체 프로세스는 크게 **입력 및 파싱**, **AI 처리 (RAG + Gemini)**, **출력 및 피드백**의 3단계로 구성됩니다.

### 1.1. 입력 데이터 및 파싱 (Step 1)
에이전트는 사용자가 제공한 비정형 문서에서 정형화된 파라미터를 추출합니다.
* **입력 데이터**: 물성 데이터(용해도·흡수부위) 요약본(`.docx`) 및 제조처 DMF 일부 자료(텍스트 기반 영문 PDF)
* **파싱 기술**: Google Cloud Document AI Layout Parser를 활용하여 문서 구조를 인식하고, 정규식(Regex)을 기반으로 핵심 파라미터를 자동 추출합니다.
* **추출 대상 파라미터**: 용해도, pKa, logP, 분자량, 흡수 부위, BCS 분류

### 1.2. AI 처리: RAG 벡터 검색 및 처방 추론 (Step 2 ~ 3)
추출된 데이터를 바탕으로 유사 사례를 검색하고 최적 처방을 추론합니다.
* **RAG 벡터 검색 (Step 2)**:
  * 파싱된 물성 데이터를 임베딩 벡터로 변환합니다. (적용 모델: `text-multilingual-embedding-002`)
  * **내부 처방 DB**를 대상으로 코사인 유사도 검색을 수행하여 Top-5 유사 처방 사례를 도출합니다. (Vertex AI Vector Search 활용)
  * 동일 인덱스에 통합 적재된 **외부 문헌 데이터**(Section 2 참조)도 RAG 검색 소스로 함께 활용됩니다.
* **처방 설계 추론 (Step 3)**:
  * Gemini 3 Pro 모델에 **'ICH Q8(R2) QbD 전문가'** 페르소나를 부여합니다.
  * 물성 데이터, 도출된 유사 사례, DMF 자료를 통합 분석합니다.
  * 환각 방지 및 일관성 확보를 위해 `JSON Schema` 강제 출력 모드를 사용하며, Temperature는 `0.2`로 설정합니다.
  * **출력 결과**: 최적 처방 3종 및 각 처방에 대한 리스크 등급(Low/Med/High)

### 1.3. 출력, 실험 및 피드백 루프 (Step 4 ~ 7)
AI의 제안을 실제 실험과 연계하고, 그 결과를 다시 학습에 반영합니다.
* **처방 도출 및 실험 (Step 4~5)**: 추론된 처방을 기반으로 Excel(`.xlsx`) 형태의 시험처방 도출표를 자동 생성하며, 연구원은 이를 바탕으로 매뉴얼 실험을 진행합니다. (레거시 PoC 개요에서는 `.xls`도 허용되나, 본 설계에서는 `.xlsx`로 표준화합니다.)
* **결과 편차 분석 (Step 6)**: 실측값과 설계 기대값 간의 Delta를 자동 계산하는 피드백 루프를 가동합니다.
  * **합격 기준**: 용출률 ≥ 85%, 함량 ≥ 98.5% → 처방 확정
  * **불합격 시**: Gemini 모델을 재호출하여 원인 분석 및 개선안을 도출하고 재시험을 계획합니다.
* **최종 보고서 저장 (Step 7)**: 최종 확정된 내용을 바탕으로 '최적 처방 가이드(`.docx`)'를 자동 생성하고, 사내 문서 관리 시스템(클라우독 / ELN)과 연동하여 저장합니다.

---

## 2. External Data Integration (Reference Sites)

에이전트는 내부 DB뿐만 아니라 제제연구에 필요한 다양한 외부 논문, 화합물, 부형제 데이터베이스와 연동하여 RAG 인덱스를 구축합니다.

| 분류 | 데이터 소스 | 수집 데이터 유형 | API 및 연동 방법 |
|---|---|---|---|
| **논문 및 문헌** | PubMed | 논문 메타데이터, 전문(XML) | NCBI Entrez E-utilities (무료 API, `esearch` → PMID 목록, `efetch` → XML 전문·초록) |
| | ScienceDirect | 초록, 메타데이터, 전문(제한적) | Elsevier Developer API (`Article Search` GET 요청, 전문은 기관 구독/TDM 계약 필요) |
| | SpringerLink | 초록, 메타데이터 | Springer Nature Meta API (등록 필요, OA 논문은 전문 URL 제공) |
| | MDPI | 논문 전문(OA), 메타데이터 | OAI-PMH, RSS 피드, 또는 직접 HTML/PDF 파싱 (전 논문 OA) |
| | Google Scholar | 검색 결과, 메타데이터 | 공식 API 없음 → SerpAPI Scholar, ScraperAPI, 또는 `scholarly` 파이썬 라이브러리 |
| | Wiley Online Library | 메타데이터, 초록 | CrossRef API (무료, `filter=member:311`), Wiley TDM API, 일부 OA 전문 직접 접근 |
| | Taylor & Francis | 메타데이터, 초록 | CrossRef API (무료, `filter=member:301`), 자체 API(계약 필요), OA는 Unpaywall API로 전문 URL 획득 |
| **화합물 정보** | PubChem | 화합물 구조, 물리화학적 특성(용해도·pKa·logP·MW) | PUG-REST API (무료, CID 기반 속성 조회) |
| | DrugBank | 약물 상호작용, 성분·경로, 약동학 데이터 | 오픈 데이터 XML/CSV 다운로드(비상업 무료) 또는 REST API(유료 라이선스) |
| **부형제 정보** | FDA IIG | 허용 부형제 목록, 최대 투여량, 제형별 한도 | FDA OpenAPI (`inactive_ingredient` 검색) 또는 CSV 다운로드 |
| | Pharma Excipients | 부형제 특성, 응용 사례, 공급업체 정보 | 공식 API 없음 → BeautifulSoup/Playwright 웹 스크래핑 |

*수집된 외부 데이터는 정제 및 청킹(Chunking)을 거쳐 Vertex AI Vector Search의 인덱스에 적재되며, Gemini 에이전트의 RAG 검색 소스로 활용됩니다. 일부 소스(PubMed, PubChem, FDA IIG 등)는 PoC101(제제연구)과 PoC103(분석연구)에서 공통으로 활용됩니다.*

---

## 3. 에이전트 아키텍처 및 시스템 요구사항

### 3.1. 컴포넌트 구성
* **문서 파싱 모듈**: Google Cloud Document AI (Layout Parser)
* **임베딩 모델**: `text-multilingual-embedding-002` (한국어 및 영문 동시 지원)
* **벡터 데이터베이스**: Vertex AI Vector Search (내부 DB 및 외부 수집 문헌 통합)
* **추론 엔진**: Gemini 3 Pro (JSON Mode, Temperature 0.2)
* **오케스트레이션**: LangChain 또는 LlamaIndex (Google Cloud Vertex AI 플러그인 연동)

### 3.2. 보안 및 규제 준수
* 입력되는 DMF 문서 등 기밀 데이터는 Google Cloud의 엔터프라이즈 보안망 내에서만 처리되어야 하며, 외부 모델 학습에 사용되지 않아야 합니다.
* 최종 처방 가이드 및 실험 피드백 로그는 감사 추적(Audit Trail)이 가능하도록 설계하여 제약 GxP 규제를 준수해야 합니다.

### 3.3. 인터페이스
* 사용자가 `.docx` 및 `.pdf` 파일을 업로드하면 백그라운드에서 전체 파이프라인이 실행되고, 최종 `.xlsx` 및 `.docx` 파일을 다운로드할 수 있는 웹 기반 UI 또는 사내 그룹웨어 플러그인 형태로 제공됩니다.
