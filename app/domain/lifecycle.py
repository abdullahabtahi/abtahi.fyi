from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict

from app.domain.models import (
    ConnectionProposal,
    DecisionCommand,
    DeferredWindow,
    ProposalStatus,
)


class ProposalTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    previous_status: ProposalStatus
    next_status: ProposalStatus
    command: DecisionCommand
    proposal: ConnectionProposal | None = None


def validate_transition(
    proposal: ConnectionProposal,
    command: DecisionCommand,
    *,
    reviewed_content: str | None = None,
    defer_window: DeferredWindow | None = None,
    dismissal_operation_id: str | None = None,
    now: datetime | None = None,
) -> ProposalTransition:
    if proposal.status is ProposalStatus.CONNECTED:
        raise ValueError("finalized proposals cannot be changed")

    current_time = now or datetime.now(timezone.utc)
    if command is DecisionCommand.UNDO:
        if proposal.status is not ProposalStatus.DISMISSED:
            raise ValueError("only dismissed proposals can be undone")
        if dismissal_operation_id != proposal.dismissal_operation_id:
            raise ValueError("undo requires the current dismissal operation")
        next_status = ProposalStatus.PENDING
    elif proposal.status is ProposalStatus.DISMISSED:
        raise ValueError("dismissed proposals can only be undone")
    if command is DecisionCommand.CONNECT:
        final_content = reviewed_content or proposal.final_reviewed_content
        if final_content is None:
            raise ValueError("connect requires final reviewed content")
        next_status = ProposalStatus.CONNECTED
    elif command is DecisionCommand.DEFER:
        if defer_window is None:
            raise ValueError("defer requires a review window")
        next_status = ProposalStatus.DEFERRED
    elif command is DecisionCommand.DISMISS:
        next_status = ProposalStatus.DISMISSED
    else:
        next_status = ProposalStatus.PENDING

    replacement_data = proposal.model_dump(mode="python")
    replacement_data["status"] = next_status
    replacement_data["revision"] = proposal.revision + 1
    if command in {DecisionCommand.CONNECT, DecisionCommand.EDIT}:
        replacement_data["final_reviewed_content"] = reviewed_content or proposal.final_reviewed_content
        replacement_data["reviewed_at"] = current_time
    if command is DecisionCommand.DEFER:
        replacement_data["defer_window"] = defer_window
        replacement_data["defer_until"] = current_time + {
            DeferredWindow.TOMORROW: timedelta(days=1),
            DeferredWindow.NEXT_WEEK: timedelta(days=7),
            DeferredWindow.LATER: timedelta(days=30),
        }[defer_window]
    if command is DecisionCommand.DISMISS:
        if not dismissal_operation_id:
            raise ValueError("dismiss requires an operation reference")
        replacement_data["dismissal_operation_id"] = dismissal_operation_id
    if command is DecisionCommand.UNDO:
        replacement_data["dismissal_operation_id"] = None
        replacement_data["defer_window"] = None
        replacement_data["defer_until"] = None
    replacement = ConnectionProposal.model_validate(replacement_data)

    return ProposalTransition(
        previous_status=proposal.status,
        next_status=next_status,
        command=command,
        proposal=replacement,
    )
