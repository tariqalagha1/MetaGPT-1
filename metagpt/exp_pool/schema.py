"""Experience schema."""

from enum import Enum
from typing import Optional

from llama_index.core.schema import TextNode
from pydantic import BaseModel, Field

MAX_SCORE = 10

DEFAULT_COLLECTION_NAME = "experience_pool"
DEFAULT_SIMILARITY_TOP_K = 2


class QueryType(str, Enum):
    """Type of query experiences."""

    EXACT = "exact"
    SEMANTIC = "semantic"


class ExperienceType(str, Enum):
    """Experience Type."""

    SUCCESS = "success"
    FAILURE = "failure"
    INSIGHT = "insight"


class EntryType(Enum):
    """Experience Entry Type."""

    AUTOMATIC = "Automatic"
    MANUAL = "Manual"


class Score(BaseModel):
    """Score in Metric."""

    val: int = Field(default=1, description="Value of the score, Between 1 and 10, higher is better.")
    reason: str = Field(default="", description="Reason for the value.")


class Metric(BaseModel):
    """Experience Metric."""

    time_cost: float = Field(default=0.000, description="Time cost, the unit is milliseconds.")
    money_cost: float = Field(default=0.000, description="Money cost, the unit is US dollars.")
    score: Score = Field(default=None, description="Score, with value and reason.")


class Trajectory(BaseModel):
    """Experience Trajectory."""

    plan: str = Field(default="", description="The plan.")
    action: str = Field(default="", description="Action for the plan.")
    observation: str = Field(default="", description="Output of the action.")
    reward: int = Field(default=0, description="Measure the action.")


class Experience(BaseModel):
    """Experience."""

    req: str = Field(..., description="")
    resp: str = Field(..., description="The type is string/json/code.")
    metric: Optional[Metric] = Field(default=None, description="Metric.")
    exp_type: ExperienceType = Field(default=ExperienceType.SUCCESS, description="The type of experience.")
    entry_type: EntryType = Field(default=EntryType.AUTOMATIC, description="Type of entry: Manual or Automatic.")
    tag: str = Field(default="", description="Tagging experience.")
    traj: Optional[Trajectory] = Field(default=None, description="Trajectory.")

    def rag_key(self):
        return self.req


class ExperienceNodeMetadata(BaseModel):
    """Metadata of ExperienceNode."""

    resp: str = Field(..., description="")


class ExperienceNode(TextNode):
    """ExperienceNode for RAG."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.excluded_llm_metadata_keys = list(ExperienceNodeMetadata.model_fields.keys())
        self.excluded_embed_metadata_keys = self.excluded_llm_metadata_keys
