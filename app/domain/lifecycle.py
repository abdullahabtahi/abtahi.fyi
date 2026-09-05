from pydantic import BaseModel, ConfigDict

from app.domain.models import ConnectionProposal, DecisionCommand, ProposalStatus


class ProposalTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    previous_status: ProposalStatus
    next_status: ProposalStatus
    command: DecisionCommand
    proposal: ConnectionProposal | None = None


def validate_transition(
    proposal: ConnectionProposal, command: DecisionCommand
) -> ProposalTransition:
    if proposal.status in {ProposalStatus.CONNECTED, ProposalStatus.DISMISSED}:
        raise ValueError("finalized proposals cannot be changed")

    if command is DecisionCommand.CONNECT:
        if proposal.final_reviewed_content is None:
            raise ValueError("connect requires final reviewed content")
        next_status = ProposalStatus.CONNECTED
    elif command is DecisionCommand.DEFER:
        next_status = ProposalStatus.DEFERRED
    elif command is DecisionCommand.DISMISS:
        next_status = ProposalStatus.DISMISSED
    else:
        next_status = ProposalStatus.PENDING

    replacement_data = proposal.model_dump(mode="python")
    replacement_data["status"] = next_status
    replacement = ConnectionProposal.model_validate(replacement_data)

    return ProposalTransition(
        previous_status=proposal.status,
        next_status=next_status,
        command=command,
        proposal=replacement,
    )
