"""
Central enum definitions shared across all modules.
Centralising here avoids circular imports and makes
state-machine logic easy to audit in one file.
"""
import enum


class UserRole(str, enum.Enum):
    claimant = "claimant"
    adjuster = "adjuster"
    admin = "admin"


class ClaimStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    in_review = "in_review"
    approved = "approved"
    rejected = "rejected"
    settled = "settled"
    closed = "closed"


class ReviewDecision(str, enum.Enum):
    approve = "approve"
    reject = "reject"
    request_info = "request_info"


# ── Valid state transitions (state machine) ───────────────────────────────────
# Key = current status, Value = set of statuses it may transition TO
CLAIM_TRANSITIONS: dict[ClaimStatus, set[ClaimStatus]] = {
    ClaimStatus.draft:      {ClaimStatus.submitted},
    ClaimStatus.submitted:  {ClaimStatus.in_review},
    ClaimStatus.in_review:  {ClaimStatus.approved, ClaimStatus.rejected},
    ClaimStatus.approved:   {ClaimStatus.settled},
    ClaimStatus.rejected:   {ClaimStatus.closed},
    ClaimStatus.settled:    {ClaimStatus.closed},
    ClaimStatus.closed:     set(),  # terminal state
}


def is_valid_transition(from_status: ClaimStatus, to_status: ClaimStatus) -> bool:
    return to_status in CLAIM_TRANSITIONS.get(from_status, set())
