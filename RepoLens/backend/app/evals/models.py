from pydantic import BaseModel


class GoldenQuestion(BaseModel):
    id: str
    question: str
    expected_files: list[str] = []
    expected_symbols: list[str] = []
    answer_must_mention: list[str] = []
    expects_refusal: bool = False


class QuestionResult(BaseModel):
    id: str
    question: str
    retrieval_hit: bool | None
    answer_correct: bool
    false_refusal: bool
    citation_validity: float
    citation_coverage: bool | None
    citation_precision: float | None
    groundedness: float | None
    refusal_correct: bool | None
    refused: bool
    latency_seconds: float
    answer: str


class MetricsSummary(BaseModel):
    retrieval_hit_at_5: float
    answer_correctness: float
    false_refusal_rate: float
    citation_validity: float
    citation_coverage: float
    citation_precision: float
    groundedness: float
    refusal_accuracy: float
    p95_latency_seconds: float
    total_questions: int
    passed_gates: bool
    gate_failures: list[str]
    results: list[QuestionResult]
