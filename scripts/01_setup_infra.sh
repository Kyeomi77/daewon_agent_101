#!/usr/bin/env bash
# ============================================================
# 01_setup_infra.sh
# GCP 인프라 프로비저닝 (최초 1회 실행)
#   - API 활성화
#   - 스테이징 버킷 생성
#   - Document AI Layout Parser 프로세서 생성
#   - Vertex AI Vector Search 인덱스/엔드포인트 생성
#
# 사전 조건: gcloud CLI 인증 완료 (gcloud auth login)
# 사용법: PROJECT_ID=daewon-rnd-poc bash scripts/01_setup_infra.sh
# ============================================================
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-daewon-rnd-poc}"
REGION="${REGION:-asia-northeast3}"
DOCAI_REGION="${DOCAI_REGION:-us}"
BUCKET="gs://${PROJECT_ID}-agent"
INDEX_DISPLAY="daewon-formulation-index"
ENDPOINT_DISPLAY="daewon-formulation-endpoint"

echo ">>> 프로젝트 설정: ${PROJECT_ID}"
gcloud config set project "${PROJECT_ID}"

echo ">>> 필요한 API 활성화"
gcloud services enable \
  aiplatform.googleapis.com \
  documentai.googleapis.com \
  storage.googleapis.com \
  --project "${PROJECT_ID}"

echo ">>> 스테이징 버킷 생성: ${BUCKET}"
if ! gsutil ls "${BUCKET}" >/dev/null 2>&1; then
  gsutil mb -l "${REGION}" "${BUCKET}"
else
  echo "    버킷이 이미 존재합니다."
fi

echo ">>> Document AI Layout Parser 프로세서 생성"
echo "    (콘솔에서 'Layout Parser' 타입으로 생성 후 PROCESSOR_ID 를 settings.yaml 에 입력)"
echo "    https://console.cloud.google.com/ai/document-ai/processors"

cat <<'NOTE'
>>> Vector Search 인덱스 생성 안내
    인덱스는 데이터가 준비된 후 scripts/02_build_index.py 에서 생성/적재합니다.
    (Streaming 또는 Batch 업데이트 인덱스). 생성 후 아래 값을
    config/settings.yaml 의 vector_search 섹션에 입력하세요:
      - index_endpoint_id
      - deployed_index_id
NOTE

echo ">>> 완료. settings.yaml 의 빈 값들을 채운 뒤 02_build_index.py 를 실행하세요."
