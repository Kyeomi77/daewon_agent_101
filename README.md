# 대원제약 제제연구 AI 에이전트 (PoC101)

물성 데이터 + DMF 자료 기반 **최적 시험 처방 3종 자동 제안 → 실험 편차 분석 → 개선안 생성**을
End-to-End 자동화하는 Google Vertex AI 기반 에이전트입니다.

> 명세서: `docs/Daewon_Agent_Spec.md` (PoC101 시나리오)
> 개발/배포 절차: `docs/DEVELOPMENT_GUIDE.md`

---

## 파이프라인

```
[Step 1] 입력 파싱        Document AI Layout Parser + Regex
[Step 2] RAG 벡터 검색    text-multilingual-embedding-002 + Vertex AI Vector Search
[Step 3] 처방 설계 추론   Gemini (QbD 페르소나, JSON Schema, T=0.2)
[Step 4-5] 처방 도출표    .xlsx 자동 생성 → 연구원 Manual 실험
[Step 6] 편차 분석        실측값 vs 기대값 Delta → 합격/불합격 판정 → 개선안
[Step 7] 최종 보고서      최적 처방 가이드 .docx → 클라우독/ELN 연동
```

## 디렉터리 구조

```
daewon_agent/
├── config/
│   └── settings.yaml              # 모든 환경 설정 (프로젝트, 모델, 임계값)
├── src/daewon_agent/
│   ├── config.py                  # 설정 로더 (pydantic)
│   ├── schemas.py                 # 입출력 JSON Schema (pydantic 모델)
│   ├── agent.py                   # LangChain 오케스트레이터 (전체 파이프라인)
│   ├── parsers/
│   │   ├── document_ai.py         # Step 1: Document AI 파싱
│   │   └── param_extractor.py     # Step 1: Regex 파라미터 추출
│   ├── rag/
│   │   ├── embedder.py            # Step 2: 임베딩
│   │   └── vector_search.py       # Step 2: Vertex AI Vector Search
│   ├── inference/
│   │   └── formulation.py         # Step 3: Gemini 처방 추론
│   ├── feedback/
│   │   └── deviation.py           # Step 6: 편차 분석 + 개선안
│   ├── outputs/
│   │   ├── xlsx_writer.py         # Step 4: 처방 도출표
│   │   └── docx_writer.py         # Step 7: 최종 가이드
│   └── external/
│       └── connectors.py          # Section 2: 외부 DB 커넥터 (PubChem 등)
├── scripts/
│   ├── 01_setup_infra.sh          # GCP 인프라 프로비저닝
│   ├── 02_build_index.py          # 외부/내부 데이터 → 벡터 인덱스 적재
│   └── run_pipeline.py            # CLI 엔트리포인트
├── tests/
│   └── test_pipeline.py           # 단위 테스트 (모킹)
├── data/sample/                   # 샘플 입출력
├── requirements.txt
└── docs/
    ├── Daewon_Agent_Spec.md
    └── DEVELOPMENT_GUIDE.md       # 0→배포 상세 절차
```

## 빠른 시작

```bash
pip install -r requirements.txt
cp config/settings.example.yaml config/settings.yaml   # 값 채우기
gcloud auth application-default login

# 인프라 + 인덱스 (최초 1회)
bash scripts/01_setup_infra.sh
python scripts/02_build_index.py

# 파이프라인 실행
python scripts/run_pipeline.py \
  --properties data/sample/properties.docx \
  --dmf data/sample/dmf.pdf \
  --out-dir ./output
```

자세한 절차는 `docs/DEVELOPMENT_GUIDE.md` 참고.
