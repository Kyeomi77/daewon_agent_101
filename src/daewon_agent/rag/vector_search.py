"""Step 2: Vertex AI Vector Search 코사인 유사도 검색.

내부 처방 DB + 외부 문헌 데이터가 통합 적재된 인덱스에서
Top-5 유사 처방 사례를 도출한다.
"""
from __future__ import annotations

import logging

from google.cloud import aiplatform
from google.cloud.aiplatform.matching_engine import (
    MatchingEngineIndexEndpoint,
)

from ..config import Settings
from ..schemas import SimilarCase

logger = logging.getLogger(__name__)


class VectorSearchClient:
    def __init__(self, settings: Settings, metadata_store: dict | None = None):
        """metadata_store: datapoint_id -> {"summary":..., "source":...} 매핑.

        실제 운영에서는 Firestore/BigQuery 등에서 조회한다.
        여기서는 인덱스 적재 시 함께 저장한 메타데이터를 주입받는다.
        """
        self.settings = settings
        self._metadata = metadata_store or {}
        aiplatform.init(
            project=settings.gcp.project_id,
            location=settings.gcp.location,
        )
        self._endpoint = MatchingEngineIndexEndpoint(
            settings.vector_search.index_endpoint_id
        )

    def search(self, query_vector: list[float]) -> list[SimilarCase]:
        top_k = self.settings.vector_search.top_k
        response = self._endpoint.find_neighbors(
            deployed_index_id=self.settings.vector_search.deployed_index_id,
            queries=[query_vector],
            num_neighbors=top_k,
        )

        cases: list[SimilarCase] = []
        for neighbors in response:
            for n in neighbors:
                meta = self._metadata.get(n.id, {})
                # MatchingEngine distance 는 코사인 거리 → 유사도 = 1 - distance
                similarity = 1.0 - float(n.distance) if n.distance is not None else 0.0
                cases.append(
                    SimilarCase(
                        case_id=n.id,
                        score=round(similarity, 4),
                        summary=meta.get("summary", f"case {n.id}"),
                        source=meta.get("source", "internal_db"),
                    )
                )
        logger.info("Top-%d 유사 사례 도출 (%d건)", top_k, len(cases))
        return cases
