from enum import Enum
from typing import Dict, List, Literal, Optional
from datetime import datetime

from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from matini.schemas import bases


class NistFunction(str, Enum):
    GOVERN = "GOVERN"
    MAP = "MAP"
    MEASURE = "MEASURE"
    MANAGE = "MANAGE"


class EthicsDimension(str, Enum):
    BIAS_FAIRNESS = "Bias & Fairness"
    PRIVACY_DATA_GOVERNANCE = "Privacy & Data Governance"
    TRANSPARENCY_ACCOUNTABILITY = "Transparency & Accountability"
    SAFETY_SOCIETAL_IMPACT = "Safety & Societal Impact"


class RiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"
    UNSCORED = "Unscored"


class AssessmentCriterion(BaseModel):
    """Static definition of one assessment item, derived from a NIST AI RMF 1.0 category.

    POC SCOPE NOTE: this is a representative subset (12 items) of the full NIST AI
    RMF Core, which has ~72 subcategories spread across GOVERN / MAP / MEASURE /
    MANAGE. The subset here was chosen to (a) give at least light coverage of all
    four NIST functions and (b) map cleanly onto the four ethics dimensions this
    project focuses on: Bias & Fairness, Privacy & Data Governance, Transparency &
    Accountability, Safety & Societal Impact. For the full study, expand this list
    using the official subcategories in NIST.AI.100-1 and re-run expert validation
    (IOC) on the expanded set.
    """
    id: str
    nist_function: NistFunction
    nist_category: str          # e.g. "GOVERN 1", "MEASURE 2 (Fair & Bias-Managed)"
    ethics_dimension: EthicsDimension
    title: str
    guiding_question: str
    # If set, this criterion is auto-tested by sending this prompt to the "subject"
    # model via Ollama, and the transcript is handed to the judge as extra evidence.
    probe_prompt: Optional[str] = None


class CriterionInput(BaseModel):
    criterion_id: str
    evidence_notes: str = ""


class RunAssessmentRequest(BaseModel):
    system_context: str = Field(
        default="",
        description="คำอธิบายบริบทโดยรวมของระบบ/โมเดลที่จะประเมิน (ผู้ประเมินกรอกเอง)",
    )
    criteria_inputs: List[CriterionInput] = Field(default_factory=list)
    run_probes: bool = True
    judge_llm_id: PydanticObjectId  # the registered LLM that scores each criterion


class CriterionResult(BaseModel):
    criterion: AssessmentCriterion
    evidence_notes: str
    probe_transcript: Optional[str] = None
    score: Optional[int] = None          # 1 (not addressed) .. 5 (fully addressed / best practice)
    risk_level: RiskLevel = RiskLevel.UNSCORED
    rationale: str = ""
    judge_error: Optional[str] = None


class BaseAssessmentReport(BaseModel):
    llm_id: PydanticObjectId
    llm_name: str
    subject_model: str
    judge_model: str  # the judge's Ollama model tag
    # Reports created before the judge became selectable have neither of these.
    judge_llm_id: Optional[PydanticObjectId] = None
    judge_llm_name: Optional[str] = None
    system_context: str
    criteria_results: List[CriterionResult]
    function_scores: Dict[str, Optional[float]]
    overall_score: Optional[float] = None
    overall_risk_level: RiskLevel = RiskLevel.UNSCORED


class AssessmentReport(bases.BaseSchema, BaseAssessmentReport):
    created_date: datetime = Field(default_factory=datetime.now)


class AssessmentJob(BaseModel):
    """Live progress of a running assessment (kept in memory only)."""
    job_id: str
    llm_id: PydanticObjectId
    status: Literal["running", "done", "error"] = "running"
    step: int = 0
    total: int = 0
    label: str = ""
    report_id: Optional[PydanticObjectId] = None
    error: Optional[str] = None
