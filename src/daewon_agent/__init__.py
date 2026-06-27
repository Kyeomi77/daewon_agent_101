"""대원제약 제제연구 AI 에이전트 (PoC101).

상위 패키지는 무거운 GCP 의존성을 지연 import 한다.
오프라인 단위 모듈(schemas, parsers, outputs)은 GCP 설치 없이 사용 가능하다.
"""
__version__ = "1.0.0"
__all__ = ["DaewonFormulationAgent", "PipelineState"]


def __getattr__(name):
    if name in ("DaewonFormulationAgent", "PipelineState"):
        from .agent import DaewonFormulationAgent, PipelineState
        return {"DaewonFormulationAgent": DaewonFormulationAgent,
                "PipelineState": PipelineState}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
