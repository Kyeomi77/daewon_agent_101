"""파이프라인 전반에서 사용하는 입출력 스키마 (JSON Schema 강제 출력 기반).

Step 1 추출 파라미터 → Step 3 처방 추론 출력 → Step 6 편차 분석까지
모든 단계가 이 스키마를 공유해 일관성을 보장한다.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Step 1: 물성 파라미터
# ---------------------------------------------------------------------------
class BCSClass(str, Enum):
    I = "I"      # 고용해도·고투과
    II = "II"    # 저용해도·고투과
    III = "III"  # 고용해도·저투과
    IV = "IV"    # 저용해도·저투과


class PhysChemParams(BaseModel):
    """Step 1 에서 Document AI + Regex 로 추출하는 핵심 파라미터."""
    api_name: Optional[str] = Field(None, description="원료의약품(API) 명")
    solubility_mg_ml: Optional[float] = Field(None, description="용해도 (mg/mL)")
    pka: Optional[float] = Field(None, description="pKa")
    logp: Optional[float] = Field(None, description="logP")
    molecular_weight: Optional[float] = Field(None, description="분자량 (g/mol)")
    absorption_site: Optional[str] = Field(None, description="흡수 부위")
    bcs_class: Optional[BCSClass] = Field(None, description="BCS 분류")
    raw_text: Optional[str] = Field(None, description="원문 파싱 텍스트 (감사 추적용)")


# ---------------------------------------------------------------------------
# Step 2: RAG 검색 결과
# ---------------------------------------------------------------------------
class SimilarCase(BaseModel):
    case_id: str
    score: float = Field(..., description="코사인 유사도")
    summary: str
    source: str = Field("internal_db", description="internal_db | external_literature")


# ---------------------------------------------------------------------------
# Step 3: 처방 추론 출력 (Gemini JSON Schema 강제 출력)
# ---------------------------------------------------------------------------
class RiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Med"
    HIGH = "High"


class ExcipientSpec(BaseModel):
    name: str = Field(..., description="부형제명")
    function: str = Field(..., description="역할 (붕해제, 결합제 등)")
    amount_mg: float = Field(..., description="처방량 (mg)")
    percent: Optional[float] = Field(None, description="비율 (%)")


class Formulation(BaseModel):
    """단일 시험 처방안."""
    formulation_id: str = Field(..., description="처방 식별자 (예: F1)")
    rationale: str = Field(..., description="설계 근거 (QbD 관점)")
    excipients: list[ExcipientSpec]
    expected_dissolution: float = Field(..., description="설계 기대 용출률 (%)")
    expected_assay: float = Field(..., description="설계 기대 함량 (%)")
    risk_level: RiskLevel
    risk_notes: Optional[str] = None


class FormulationProposal(BaseModel):
    """Step 3 최종 출력: 최적 처방 3종."""
    api_name: str
    bcs_class: Optional[BCSClass] = None
    formulations: list[Formulation] = Field(..., min_length=1)
    cited_cases: list[str] = Field(default_factory=list, description="참조 유사 사례 ID")


# ---------------------------------------------------------------------------
# Step 6: 편차 분석
# ---------------------------------------------------------------------------
class ExperimentResult(BaseModel):
    """연구원이 입력하는 실측 결과."""
    formulation_id: str
    measured_dissolution: float
    measured_assay: float


class DeviationAnalysis(BaseModel):
    formulation_id: str
    delta_dissolution: float = Field(..., description="실측 - 기대 (용출률)")
    delta_assay: float = Field(..., description="실측 - 기대 (함량)")
    passed: bool
    improvement_plan: Optional[str] = Field(
        None, description="불합격 시 Gemini 가 생성한 개선안"
    )


# Gemini responseSchema 로 넘길 dict (Vertex AI 호환)
def formulation_response_schema(count: int = 3) -> dict:
    """Gemini JSON 강제 출력용 responseSchema 를 반환."""
    return {
        "type": "object",
        "properties": {
            "api_name": {"type": "string"},
            "bcs_class": {"type": "string", "enum": ["I", "II", "III", "IV"]},
            "formulations": {
                "type": "array",
                "minItems": count,
                "maxItems": count,
                "items": {
                    "type": "object",
                    "properties": {
                        "formulation_id": {"type": "string"},
                        "rationale": {"type": "string"},
                        "excipients": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "function": {"type": "string"},
                                    "amount_mg": {"type": "number"},
                                    "percent": {"type": "number"},
                                },
                                "required": ["name", "function", "amount_mg"],
                            },
                        },
                        "expected_dissolution": {"type": "number"},
                        "expected_assay": {"type": "number"},
                        "risk_level": {"type": "string", "enum": ["Low", "Med", "High"]},
                        "risk_notes": {"type": "string"},
                    },
                    "required": [
                        "formulation_id", "rationale", "excipients",
                        "expected_dissolution", "expected_assay", "risk_level",
                    ],
                },
            },
            "cited_cases": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["api_name", "formulations"],
    }
