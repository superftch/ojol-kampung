"""Exceptions shared by the game adapter and worker."""


class StopRequested(Exception):
    """Raised when an operator or session limit requests worker shutdown."""


class HttpCoreError(RuntimeError):
    """Domain-categorized error raised by the KampungSebelah HTTP adapter."""

    def __init__(self, message, category="schema", recoverable=False, path=None):
        super().__init__(message)
        self.category, self.recoverable = category, recoverable
        self.stage = "http." + category
        self.path = path
