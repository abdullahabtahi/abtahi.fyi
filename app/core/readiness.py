class ReadinessState:
    def __init__(self) -> None:
        self._failure_reason: str | None = "initializing"

    @property
    def is_ready(self) -> bool:
        return self._failure_reason is None

    def mark_ready(self) -> None:
        self._failure_reason = None

    def mark_failed(self, reason: str) -> None:
        self._failure_reason = reason
