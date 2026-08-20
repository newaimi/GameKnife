from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import partial
from typing import Protocol

from gameknife_core import JobRecord

from .job_types import JOB_TYPE_REGISTRY, JobTypeRegistry


JobExecutionHandler = Callable[[str, str], None]
JobResolver = Callable[[str, str], JobRecord | None]
JobRunner = Callable[[], None]
JobScheduler = Callable[[JobRunner], None]


class JobDispatcher(Protocol):
    """Dispatch an already-persisted job through the runtime selected by the application."""

    def dispatch(self, job_id: str, workspace_id: str) -> None:
        ...


class InProcessJobDispatcher:
    """Dispatch registered jobs without adding a broker dependency to Community."""

    def __init__(
        self,
        job_resolver: JobResolver,
        handlers: Mapping[str, JobExecutionHandler],
        *,
        scheduler: JobScheduler | None = None,
        registry: JobTypeRegistry = JOB_TYPE_REGISTRY,
    ) -> None:
        known_executors = {spec.executor for spec in registry.values()}
        unknown_executors = sorted(set(handlers) - known_executors)
        if unknown_executors:
            raise ValueError(f"Unknown job executors: {', '.join(unknown_executors)}")
        self._job_resolver = job_resolver
        self._handlers = dict(handlers)
        self._scheduler = scheduler or _run_now
        self._registry = registry

    def dispatch(self, job_id: str, workspace_id: str) -> None:
        job = self._job_resolver(job_id, workspace_id)
        if job is None:
            raise RuntimeError(f"Cannot dispatch missing job: {job_id}")
        spec = self._registry.require(job.job_type)
        handler = self._handlers.get(spec.executor)
        if handler is None:
            raise RuntimeError(f"No in-process handler registered for executor: {spec.executor}")
        # Passing only stable identifiers keeps the handler boundary compatible with durable dispatchers.
        self._scheduler(partial(handler, job_id, workspace_id))


def _run_now(runner: JobRunner) -> None:
    runner()
