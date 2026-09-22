"""Controlled exception hierarchy. Every critical error pauses the row safely."""


class AgentError(Exception):
    """Base class. `step` names the workflow step where it happened."""

    step: str = "UNKNOWN"

    def __init__(self, message: str, step: str | None = None):
        super().__init__(message)
        if step:
            self.step = step


class LoginRequiredError(AgentError):
    step = "LOGIN"


class CaptchaDetectedError(AgentError):
    step = "VERIFICATION"


class UnexpectedPageError(AgentError):
    pass


class ResumeNotFoundError(AgentError):
    step = "RESUME_SELECTION"


class ApplicationFailedError(AgentError):
    step = "APPLICATION"


class CompanyPageError(AgentError):
    step = "COMPANY_PAGE"


class PeopleSearchError(AgentError):
    step = "PEOPLE_SEARCH"


class ConnectionRequestError(AgentError):
    step = "CONNECTION"


class UnknownUIError(AgentError):
    pass


class ExcelValidationError(AgentError):
    step = "EXCEL"


class UserAbortError(AgentError):
    """The user chose to stop during a human-intervention prompt."""

    step = "USER_ABORT"


class JobClosedError(ApplicationFailedError):
    """The posting no longer accepts applications - skip the row, not a failure."""
