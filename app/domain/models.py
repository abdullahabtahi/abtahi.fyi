from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator


NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ProposalStatus(StrEnum):
    PENDING = "PENDING"
    DEFERRED = "DEFERRED"
    CONNECTED = "CONNECTED"
    DISMISSED = "DISMISSED"


class EdgeType(StrEnum):
    SUPPORTS = "supports"
    CHALLENGES = "challenges"
    EXAMPLE_OF = "example_of"
    APPLICATION_OF = "application_of"
    PREREQUISITE_FOR = "prerequisite_for"
    DEVELOPS_INTO = "develops_into"
    SUPERSEDED_BY = "superseded_by"
    RELATED_TO = "related_to"


class MatchStrength(StrEnum):
    DIRECT = "DIRECT"
    ADJACENT = "ADJACENT"


class DecisionCommand(StrEnum):
    CONNECT = "CONNECT"
    DEFER = "DEFER"
    DISMISS = "DISMISS"
    EDIT = "EDIT"


class DeferredWindow(StrEnum):
    TOMORROW = "TOMORROW"
    NEXT_WEEK = "NEXT_WEEK"
    LATER = "LATER"


class SourceRevision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: NonEmptyText
    canonical_url: NonEmptyText
    title: NonEmptyText
    author: NonEmptyText
    published_at: datetime
    content_hash: NonEmptyText


class ConnectionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: NonEmptyText
    source_revision_id: NonEmptyText
    concept_id: NonEmptyText
    edge_type: EdgeType
    match_strength: MatchStrength
    excerpt: NonEmptyText
    location: NonEmptyText
    rationale: NonEmptyText
    uncertainty: NonEmptyText
    learning_payoff: NonEmptyText
    proposed_cited_addition: NonEmptyText
    analogy: NonEmptyText | None = None
    difference: NonEmptyText | None = None
    distinction_impact: NonEmptyText | None = None
    final_reviewed_content: NonEmptyText | None = None
    status: ProposalStatus = ProposalStatus.PENDING

    @model_validator(mode="after")
    def validate_match_and_final_content(self) -> "ConnectionProposal":
        if self.match_strength is MatchStrength.ADJACENT and not all(
            (self.analogy, self.difference, self.distinction_impact)
        ):
            raise ValueError(
                "adjacent proposals require analogy, difference, and distinction impact"
            )
        if (
            self.status is ProposalStatus.CONNECTED
            and self.final_reviewed_content is None
        ):
            raise ValueError("connected proposals require final reviewed content")
        return self


class CandidateConcept(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: NonEmptyText
    name: NonEmptyText
    course_grounding: NonEmptyText
    definition: NonEmptyText
    rationale: NonEmptyText
    proposed_links: tuple[NonEmptyText, ...]
    learner_approved: bool = False
    active: bool = False

    @model_validator(mode="after")
    def validate_activation(self) -> "CandidateConcept":
        if self.active and not self.learner_approved:
            raise ValueError("candidate concepts require learner approval before activation")
        return self

class Identity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    uid: NonEmptyText
    email: NonEmptyText

class ForbiddenError(Exception):
    """Raised when identity verification fails."""
    pass

class MarkdownChunk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    
    chunk_id: NonEmptyText
    breadcrumb: str
    text: NonEmptyText
    embedding: list[float] | None = None

class InteractionType(StrEnum):
    PROPOSAL_REVIEW = "proposal_review"
    REFLECTION_SUBMIT = "reflection_submit"
    STUDY_SEARCH = "study_search"

class InteractionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    
    interaction_id: NonEmptyText
    user_id: NonEmptyText
    interaction_type: InteractionType
    proposal_id: NonEmptyText | None = None
    concept_id: NonEmptyText | None = None
    user_decision: DecisionCommand | None = None
    reflection_text: str | None = None
    diagnostic_response: str | None = None
    timestamp: datetime

    @model_validator(mode="after")
    def validate_proposal_review(self) -> "InteractionRecord":
        if self.interaction_type == InteractionType.PROPOSAL_REVIEW:
            if not self.proposal_id or not self.user_decision:
                raise ValueError("proposal_id and user_decision required for proposal review")
        return self

class ConceptNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    
    slug: NonEmptyText
    title: NonEmptyText
    module: NonEmptyText
    synthesis: NonEmptyText
    citations: list[NonEmptyText] = []

class EdgeReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: NonEmptyText
    target_id: NonEmptyText
    edge_type: str | None = None

from typing import Literal

class ContentItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: NonEmptyText
    plane: Literal["public", "private"]
    type: Literal["note", "link", "theme", "inquiry"]
    title: NonEmptyText
    metadata: dict
    raw_content: str
    html_content: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
