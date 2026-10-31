from .models import ComplaintStatus as S


def _values(*members):
    return frozenset(m.value for m in members)


# Source of truth for permitted transitions. CLOSED is terminal and is reachable
# only through the close endpoint (see CLOSE_FROM), never through the status endpoint.
ALLOWED_TRANSITIONS = {
    S.SUBMITTED.value: _values(S.ASSIGNED),
    S.ASSIGNED.value: _values(S.IN_PROGRESS),
    S.IN_PROGRESS.value: _values(S.RESOLVED),
    S.RESOLVED.value: _values(S.IN_PROGRESS, S.CLOSED),
    S.CLOSED.value: frozenset(),
}
CLOSE_FROM = S.RESOLVED.value

_LABEL_TO_STATUS = {label.lower(): value for value, label in S.choices}


def parse_status(text):
    """'In Progress', 'in progress', 'IN_PROGRESS' -> 'IN_PROGRESS'; unknown -> None."""
    normalized = " ".join((text or "").replace("_", " ").lower().split())
    return _LABEL_TO_STATUS.get(normalized)


def can_transition(old, new):
    """Transitions allowed through the status endpoint (closing is separate)."""
    return new != S.CLOSED.value and new in ALLOWED_TRANSITIONS.get(old, frozenset())
