"""Section 2: 외부 데이터 소스 커넥터.

명세서의 외부 DB 중 무료·공개 API 위주로 구현한다.
- PubChem PUG-REST: 화합물 물리화학적 특성 보강
- PubMed E-utilities: 관련 문헌 메타데이터
- FDA IIG (openFDA): 허용 부형제/최대 투여량

수집 데이터는 RAG 인덱스 적재(scripts/02_build_index.py) 또는
Step 1 파라미터 보강에 활용한다.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

_TIMEOUT = 20


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def _get(url: str, params: dict | None = None) -> requests.Response:
    resp = requests.get(url, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp


class PubChemConnector:
    """PubChem PUG-REST: 화합물명 → 물리화학적 특성."""

    def __init__(self, base_url: str = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"):
        self.base_url = base_url.rstrip("/")

    def get_properties(self, compound_name: str) -> Optional[dict]:
        props = "MolecularWeight,XLogP,TPSA,IUPACName"
        url = (
            f"{self.base_url}/compound/name/{requests.utils.quote(compound_name)}"
            f"/property/{props}/JSON"
        )
        try:
            data = _get(url).json()
            table = data["PropertyTable"]["Properties"][0]
            return {
                "molecular_weight": table.get("MolecularWeight"),
                "logp": table.get("XLogP"),
                "tpsa": table.get("TPSA"),
                "iupac_name": table.get("IUPACName"),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("PubChem 조회 실패(%s): %s", compound_name, e)
            return None


class PubMedConnector:
    """NCBI Entrez E-utilities: 키워드 → PMID 목록 → 메타데이터."""

    def __init__(
        self,
        base_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        api_key: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def search_pmids(self, query: str, retmax: int = 10) -> list[str]:
        params = {"db": "pubmed", "term": query, "retmax": retmax, "retmode": "json"}
        if self.api_key:
            params["api_key"] = self.api_key
        try:
            data = _get(f"{self.base_url}/esearch.fcgi", params).json()
            return data["esearchresult"]["idlist"]
        except Exception as e:  # noqa: BLE001
            logger.warning("PubMed esearch 실패: %s", e)
            return []

    def fetch_abstracts(self, pmids: list[str]) -> str:
        if not pmids:
            return ""
        params = {
            "db": "pubmed", "id": ",".join(pmids),
            "rettype": "abstract", "retmode": "text",
        }
        if self.api_key:
            params["api_key"] = self.api_key
        try:
            return _get(f"{self.base_url}/efetch.fcgi", params).text
        except Exception as e:  # noqa: BLE001
            logger.warning("PubMed efetch 실패: %s", e)
            return ""


class FDAIIGConnector:
    """openFDA: 부형제명 → 라벨 정보 (허용 부형제 검증)."""

    def __init__(self, base_url: str = "https://api.fda.gov/drug/label.json"):
        self.base_url = base_url

    def search_inactive_ingredient(self, excipient: str, limit: int = 5) -> list[dict]:
        params = {"search": f"inactive_ingredient:{excipient}", "limit": limit}
        try:
            data = _get(self.base_url, params).json()
            return data.get("results", [])
        except Exception as e:  # noqa: BLE001
            logger.warning("openFDA 조회 실패(%s): %s", excipient, e)
            return []
