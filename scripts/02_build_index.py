#!/usr/bin/env python
"""02_build_index.py — 내부/외부 데이터를 Vertex AI Vector Search 인덱스에 적재.

흐름:
  1. 내부 처방 DB (CSV/JSONL) 로드
  2. (선택) 외부 문헌 수집 (PubMed) 후 병합
  3. text-multilingual-embedding-002 로 임베딩
  4. JSONL datapoint 파일 생성 → GCS 업로드
  5. Vector Search 인덱스 생성/업데이트 + 엔드포인트 배포

운영 환경에서는 데이터 규모에 따라 Batch 인덱스를 권장한다.
이 스크립트는 절차 예시이며, 데이터 경로는 환경에 맞게 조정한다.
"""
from __future__ import annotations

import json
import sys
import argparse
import logging
from pathlib import Path

# 패키지 import 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from daewon_agent.config import get_settings  # noqa: E402
from daewon_agent.rag.embedder import Embedder  # noqa: E402
from daewon_agent.external.connectors import PubMedConnector  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_index")


def load_internal_db(path: Path) -> list[dict]:
    """내부 처방 DB(JSONL) 로드. 각 레코드: {id, summary}."""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    logger.info("내부 DB %d건 로드", len(records))
    return records


def collect_external(query: str, retmax: int) -> list[dict]:
    """PubMed 에서 관련 문헌 초록 수집."""
    settings = get_settings()
    src = settings.external_sources.get("pubmed", {})
    if not src.get("enabled"):
        return []
    conn = PubMedConnector(
        base_url=src.get("base_url", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"),
        api_key=src.get("api_key", ""),
    )
    pmids = conn.search_pmids(query, retmax=retmax)
    records = []
    for pmid in pmids:
        abstract = conn.fetch_abstracts([pmid])
        if abstract.strip():
            records.append({
                "id": f"pubmed_{pmid}",
                "summary": abstract[:1000],
                "source": "external_literature",
            })
    logger.info("외부 문헌 %d건 수집", len(records))
    return records


def build_datapoints(records: list[dict], embedder: Embedder) -> list[dict]:
    texts = [r["summary"] for r in records]
    vectors = embedder.embed_documents(texts)
    datapoints = []
    for r, v in zip(records, vectors):
        datapoints.append({"id": r["id"], "embedding": v})
    return datapoints


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--internal-db", default="data/sample/internal_db.jsonl")
    ap.add_argument("--external-query", default="solid dispersion BCS class II formulation")
    ap.add_argument("--external-retmax", type=int, default=20)
    ap.add_argument("--out", default="data/datapoints.json")
    ap.add_argument("--skip-external", action="store_true")
    args = ap.parse_args()

    settings = get_settings()
    embedder = Embedder(settings)

    records: list[dict] = []
    internal_path = Path(args.internal_db)
    if internal_path.exists():
        records += [
            {**r, "source": r.get("source", "internal_db")}
            for r in load_internal_db(internal_path)
        ]
    else:
        logger.warning("내부 DB 파일 없음: %s", internal_path)

    if not args.skip_external:
        records += collect_external(args.external_query, args.external_retmax)

    if not records:
        logger.error("적재할 데이터가 없습니다.")
        sys.exit(1)

    datapoints = build_datapoints(records, embedder)

    # 메타데이터 별도 저장 (vector_search 조회 시 주입)
    metadata = {r["id"]: {"summary": r["summary"], "source": r["source"]}
                for r in records}
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(datapoints, ensure_ascii=False), encoding="utf-8")
    Path(out_path.with_name("metadata.json")).write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logger.info("Datapoint %d건 생성 → %s", len(datapoints), out_path)
    logger.info(
        "다음 단계: 이 JSONL 을 GCS 에 업로드하고 "
        "aiplatform.MatchingEngineIndex.create_tree_ah_index(...) 로 인덱스를 생성/배포하세요. "
        "절차는 docs/DEVELOPMENT_GUIDE.md 의 'Vector Search 인덱스 구축' 참고."
    )


if __name__ == "__main__":
    main()
