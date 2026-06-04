from __future__ import annotations


class WorkflowInputNotFoundError(ValueError):
    pass


class WorkflowModelNotInstalledError(ValueError):
    pass


class WorkflowServiceUnavailableError(ValueError):
    pass


class WorkflowValidationError(ValueError):
    pass
