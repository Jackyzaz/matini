from enum import Enum
from typing import Dict, List, Literal, Optional
from datetime import datetime
from uuid import uuid4

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field

from matini.schemas import bases
from matini.schemas.evidence import CriterionEvidence


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


class RubricLevel(BaseModel):
    """One of the 5 scoring levels of a criterion, shared by the human assessor and the LLM judge."""
    score: int = Field(ge=1, le=5)
    label: str
    description: str


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
    # 5 levels (score 1..5). Like the criteria themselves, the rubric wording is a POC draft and
    # still needs expert validation (IOC) before the real study.
    rubric: List[RubricLevel] = Field(default_factory=list)
    # If set, this criterion is auto-tested by sending each prompt to the "subject"
    # model via Ollama, and the replies are handed to the judge (or the human) as evidence.
    probe_prompts: List[str] = Field(default_factory=list)
    # Deprecated single prompt: only present in criteria embedded in reports created before probe_prompts.
    probe_prompt: Optional[str] = None


class RunAssessmentRequest(BaseModel):
    run_probes: bool = True
    judge_llm_id: PydanticObjectId  # the registered LLM that scores each criterion


class ProbeResult(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    prompt: str
    # "builtin" comes from criterion.probe_prompts; "custom" was typed by the human assessor
    # and exists only in that report.
    source: Literal["builtin", "custom"] = "builtin"
    response: Optional[str] = None
    error: Optional[str] = None
    created_date: datetime = Field(default_factory=datetime.now)


class CriterionResult(BaseModel):
    criterion: AssessmentCriterion
    evidence_notes: str  # kept so reports created before profiles still open
    # Snapshot of the profile's entry for this criterion at run time (files by id + name only).
    evidence: Optional[CriterionEvidence] = None
    evidence_files: Dict[str, str] = Field(default_factory=dict)  # file_id -> filename
    probes: List[ProbeResult] = Field(default_factory=list)
    probe_transcript: Optional[str] = None  # single-probe reports from before `probes` existed
    score: Optional[int] = None          # 1 (not addressed) .. 5 (fully addressed / best practice)
    risk_level: RiskLevel = RiskLevel.UNSCORED
    rationale: str = ""
    judge_error: Optional[str] = None


class BaseAssessmentReport(BaseModel):
    llm_id: PydanticObjectId
    llm_name: str
    subject_model: str
    judge_model: str = ""  # the judge's Ollama model tag (empty for human assessments)
    # Reports created before human assessment are all "llm" and "completed".
    judge_type: Literal["llm", "human"] = "llm"
    assessor_name: Optional[str] = None  # human assessments only (there is no auth, so typed in)
    status: Literal["draft", "completed", "delete"] = "completed"
    completed_date: Optional[datetime] = None
    # Reports created before the judge became selectable have neither of these.
    judge_llm_id: Optional[PydanticObjectId] = None
    judge_llm_name: Optional[str] = None
    system_context: str  # the rendered profile context, as the judge saw it
    profile_updated_date: Optional[datetime] = None
    criteria_results: List[CriterionResult]
    function_scores: Dict[str, Optional[float]]
    overall_score: Optional[float] = None
    overall_risk_level: RiskLevel = RiskLevel.UNSCORED


class StartManualRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    assessor_name: str = Field(min_length=1)


class HumanScoreRequest(BaseModel):
    score: Optional[int] = Field(default=None, ge=1, le=5)  # None clears the score
    rationale: str = ""


class CreateProbeRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    prompt: str = Field(min_length=1)


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
