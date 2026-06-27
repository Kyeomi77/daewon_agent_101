"""Step 1: 정규식 기반 핵심 파라미터 추출.

Document AI 가 추출한 평문 텍스트에서 용해도/pKa/logP/분자량/흡수부위/BCS 를
정규식으로 추출해 PhysChemParams 구조체로 정규화한다.
"""
from __future__ import annotations

import re
import logging
from typing import Optional

from ..schemas import PhysChemParams, BCSClass

logger = logging.getLogger(__name__)

# 숫자(소수/지수 포함) 패턴
_NUM = r"([-+]?\d+(?:\.\d+)?)"

_PATTERNS = {
    "solubility": re.compile(
        rf"(?:용해도|solubility)\s*[:=]?\s*{_NUM}\s*(?:mg/?m[lL]|mg·mL)",
        re.IGNORECASE,
    ),
    "pka": re.compile(rf"pKa\s*[:=]?\s*{_NUM}", re.IGNORECASE),
    "logp": re.compile(rf"log\s*P\s*[:=]?\s*{_NUM}", re.IGNORECASE),
    "mw": re.compile(
        rf"(?:분자량|molecular\s*weight|MW)\s*[:=]?\s*{_NUM}",
        re.IGNORECASE,
    ),
    "bcs": re.compile(
        r"BCS\s*(?:class|분류)?\s*[:=]?\s*(I{1,3}V?|IV|[1-4])",
        re.IGNORECASE,
    ),
}

# 흡수 부위 키워드 매핑 (긴 키워드 우선, "부위" 같은 라벨 오탐 방지)
_ABSORPTION_KEYWORDS = [
    "십이지장", "소장", "대장", "공장", "회장",
    "small intestine", "duodenum", "jejunum", "ileum", "colon", "stomach",
    "위",  # 단독 '위'는 마지막에 평가 (라벨어 '부위' 와 충돌 방지)
]

# 흡수 부위 라벨만 떼어내고 값 영역에서 키워드를 찾기 위한 패턴
_ABSORPTION_LABEL = re.compile(
    r"(?:흡수\s*부위|absorption\s*site)\s*[:=]?\s*([^\n]+)",
    re.IGNORECASE,
)

_BCS_NORMALIZE = {
    "1": "I", "2": "II", "3": "III", "4": "IV",
    "I": "I", "II": "II", "III": "III", "IV": "IV",
}


def _search_float(pattern: re.Pattern, text: str) -> Optional[float]:
    m = pattern.search(text)
    if m:
        try:
            return float(m.group(1))
        except (ValueError, IndexError):
            return None
    return None


def _extract_bcs(text: str) -> Optional[BCSClass]:
    m = _PATTERNS["bcs"].search(text)
    if not m:
        return None
    raw = m.group(1).upper()
    normalized = _BCS_NORMALIZE.get(raw)
    if normalized:
        return BCSClass(normalized)
    return None


def _extract_absorption_site(text: str) -> Optional[str]:
    # 1) "흡수 부위: XXX" 라벨이 있으면 값 영역에서만 키워드 탐색
    label_match = _ABSORPTION_LABEL.search(text)
    search_space = label_match.group(1) if label_match else text
    for kw in _ABSORPTION_KEYWORDS:
        if kw.lower() in search_space.lower():
            return kw
    return None


def _extract_api_name(text: str) -> Optional[str]:
    # "원료명 / API / 화합물명 : XXX" 형태 우선 탐색
    m = re.search(
        r"(?:원료명|API|화합물명|compound|drug\s*name)\s*[:=]\s*([^\n]+)",
        text, re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()[:120]
    return None


def extract_parameters(text: str) -> PhysChemParams:
    """평문 텍스트에서 PhysChemParams 추출."""
    params = PhysChemParams(
        api_name=_extract_api_name(text),
        solubility_mg_ml=_search_float(_PATTERNS["solubility"], text),
        pka=_search_float(_PATTERNS["pka"], text),
        logp=_search_float(_PATTERNS["logp"], text),
        molecular_weight=_search_float(_PATTERNS["mw"], text),
        absorption_site=_extract_absorption_site(text),
        bcs_class=_extract_bcs(text),
        raw_text=text[:5000],  # 감사 추적용 (앞부분만 보관)
    )
    missing = [k for k, v in params.model_dump().items()
               if v is None and k != "raw_text"]
    if missing:
        logger.warning("추출되지 않은 파라미터: %s", missing)
    return params
