# 개발 및 배포 상세 절차 (DEVELOPMENT GUIDE)

대원제약 제제연구 AI 에이전트(PoC101)를 Google Vertex AI 환경에서 0부터 구축·배포하는 단계별 절차입니다.

---

## 0. 사전 준비

| 항목 | 내용 |
|---|---|
| GCP 프로젝트 | 결제 활성화된 프로젝트 (예: `daewon-rnd-poc`) |
| IAM 권한 | Vertex AI User, Document AI Editor, Storage Admin |
| 로컬 도구 | `gcloud` CLI, Python 3.10+ |
| 리전 | 데이터 거버넌스상 `asia-northeast3`(서울) 권장. 단, Document AI 는 `us`/`eu` 만 지원하므로 분리 구성 |

```bash
# 인증
gcloud auth login
gcloud auth application-default login
gcloud config set project daewon-rnd-poc

# 의존성 설치
pip install -r requirements.txt
```

---

## 1. 인프라 프로비저닝

```bash
PROJECT_ID=daewon-rnd-poc bash scripts/01_setup_infra.sh
```

이 스크립트는 API 활성화, 스테이징 버킷 생성을 수행합니다. 이어서 콘솔 작업 2건이 필요합니다.

### 1.1 Document AI Layout Parser 프로세서 생성
1. 콘솔 → Document AI → Processors → **Create Processor**
2. 타입: **Layout Parser** 선택, 리전 `us`
3. 생성된 **Processor ID** 를 `config/settings.yaml` 의 `document_ai.processor_id` 에 입력

### 1.2 설정 파일 작성
```bash
cp config/settings.example.yaml config/settings.yaml
# settings.yaml 의 project_id, processor_id 등을 채움
```

---

## 2. Vector Search 인덱스 구축 (Step 2 기반)

### 2.1 데이터 준비 및 임베딩
내부 처방 DB(JSONL)와 외부 문헌(PubMed)을 임베딩해 datapoint 파일을 생성합니다.

```bash
python scripts/02_build_index.py \
  --internal-db data/sample/internal_db.jsonl \
  --external-query "solid dispersion BCS class II bioavailability" \
  --out data/datapoints.json
```

산출물: `data/datapoints.json`(임베딩), `data/metadata.json`(사례 요약·출처).

### 2.2 인덱스 생성 및 엔드포인트 배포
datapoint JSONL 을 GCS 에 업로드한 뒤 인덱스를 생성합니다.

```python
from google.cloud import aiplatform
aiplatform.init(project="daewon-rnd-poc", location="asia-northeast3")

# (1) datapoint 파일을 GCS 에 업로드 후 해당 경로 지정
index = aiplatform.MatchingEngineIndex.create_tree_ah_index(
    display_name="daewon-formulation-index",
    contents_delta_uri="gs://daewon-rnd-poc-agent/index_data/",
    dimensions=768,                       # text-multilingual-embedding-002
    approximate_neighbors_count=50,
    distance_measure_type="COSINE_DISTANCE",
)

# (2) 엔드포인트 생성 + 배포
endpoint = aiplatform.MatchingEngineIndexEndpoint.create(
    display_name="daewon-formulation-endpoint",
    public_endpoint_enabled=True,
)
endpoint.deploy_index(index=index, deployed_index_id="daewon_formulation_idx")
```

배포 후 `index_endpoint_id`, `deployed_index_id` 를 `settings.yaml` 에 입력합니다.
(인덱스 배포는 20~40분 소요)

---

## 3. 모델 확인

`settings.yaml` 의 `models` 섹션:
- **임베딩**: `text-multilingual-embedding-002` (768차원, 한국어·영문)
- **추론**: `generation_model` — 콘솔(Vertex AI → Model Garden)에서 현재 사용 가능한 Gemini Pro 모델명을 확인 후 입력하세요. 명세서는 "Gemini 3 Pro"로 기술되어 있으나, 실제 API 호출명은 리전·시점에 따라 다릅니다. 사용 가능 모델 조회:

```bash
gcloud ai models list --region=asia-northeast3 2>/dev/null
# 또는 Model Garden 콘솔에서 확인
```

---

## 4. 파이프라인 실행

### 4.1 처방 제안 (Step 1~5)
```bash
python scripts/run_pipeline.py \
  --properties data/sample/properties.docx \
  --dmf data/sample/dmf.pdf \
  --out-dir ./output \
  --metadata data/metadata.json
```
→ `output/처방도출표.xlsx` 생성. 연구원이 이를 받아 Manual 실험 진행.

### 4.2 실험 결과 반영 + 최종 보고서 (Step 6~7)
실험 결과를 JSON 으로 작성한 뒤 동일 명령에 `--results` 추가:

```json
[
  {"formulation_id": "F1", "measured_dissolution": 90.5, "measured_assay": 99.1},
  {"formulation_id": "F2", "measured_dissolution": 72.0, "measured_assay": 97.8}
]
```

```bash
python scripts/run_pipeline.py \
  --properties data/sample/properties.docx --dmf data/sample/dmf.pdf \
  --out-dir ./output --results data/sample/results.json
```
→ 합격 기준(용출 ≥ 85%, 함량 ≥ 98.5%) 판정, 불합격 처방은 Gemini 개선안 생성,
`output/최적처방가이드.docx` 저장.

---

## 5. 테스트

```bash
pytest tests/ -v
```
GCP 호출 없이 동작하는 단위 모듈(파라미터 추출, xlsx/docx 생성, 편차 분석 로직)을 검증합니다.

---

## 6. Vertex AI Agent Engine 배포 (운영 전환)

CLI 파이프라인을 관리형 에이전트로 배포하려면 Agent Engine(구 Reasoning Engine)을 사용합니다.

```python
import vertexai
from vertexai.preview import reasoning_engines
from daewon_agent import DaewonFormulationAgent

vertexai.init(
    project="daewon-rnd-poc",
    location="asia-northeast3",
    staging_bucket="gs://daewon-rnd-poc-agent",
)

class DeployedAgent:
    def set_up(self):
        self.agent = DaewonFormulationAgent()
    def query(self, properties_path: str, dmf_path: str, out_dir: str):
        state = self.agent.propose(properties_path, dmf_path, out_dir)
        return {"xlsx": str(state.xlsx_path),
                "formulations": [f.model_dump() for f in state.proposal.formulations]}

remote_agent = reasoning_engines.ReasoningEngine.create(
    DeployedAgent(),
    requirements="requirements.txt",
    display_name="daewon-formulation-agent",
)
print(remote_agent.resource_name)
```

> 입력 파일은 GCS 경로로 전달하고, 출력은 GCS/서명 URL 로 반환하도록 인터페이스를 조정하세요.

---

## 7. 보안 및 GxP 준수 (명세서 3.2)

- **데이터 격리**: DMF 등 기밀 문서는 VPC-SC 경계 내에서 처리. Vertex AI 는 고객 데이터를 모델 학습에 사용하지 않음(기본 정책).
- **감사 추적**: `settings.yaml` 의 `logging.audit_trail: true` 로 입력 파라미터·모델·합격기준·판정결과를 로그에 기록. 운영 시 Cloud Logging → BigQuery 싱크로 영구 보관 권장.
- **ELN 연동**: `outputs/docx_writer.py` 산출물을 `agent._push_to_eln()` 에서 클라우독/ELN API 로 업로드하도록 구현(현재 스텁).

---

## 8. 단계 ↔ 모듈 매핑

| Step | 명세서 단계 | 구현 모듈 |
|---|---|---|
| 1 | 입력 파싱 | `parsers/document_ai.py`, `parsers/param_extractor.py` |
| 2 | RAG 벡터 검색 | `rag/embedder.py`, `rag/vector_search.py` |
| 3 | 처방 설계 추론 | `inference/formulation.py` |
| 4 | 처방 도출표 | `outputs/xlsx_writer.py` |
| 5 | Manual 실험 | (외부 — 연구원) |
| 6 | 편차 분석 | `feedback/deviation.py` |
| 7 | 최종 보고서 | `outputs/docx_writer.py` |
| 부록 | 외부 DB | `external/connectors.py` |
| 전체 | 오케스트레이션 | `agent.py` |
