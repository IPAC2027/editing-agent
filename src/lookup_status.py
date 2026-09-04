"""Per-run record of which external authorities actually answered.

The reason this module exists: every lookup in this codebase used to swallow its
exception and return ``None``, so "Crossref has no DOI for this reference" and
"we had no network" produced identical output.  An editor cannot act on that.

Usage::

    from src.lookup_status import STATUS

    with STATUS.attempt("crossref") as ok:
        ...                     # do the request
        ok.succeeded()          # only on a real 2xx answer

    if not STATUS.reachable("crossref"):
        ...                     # say "not checked", never "not found"

The status object is process-global on purpose: a prescreen run is a single
logical operation and every check needs the same view of what was reachable.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class ServiceState:
    name: str
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    last_error: str = ""

    @property
    def reachable(self) -> bool:
        """True once the service has answered at least one request successfully.

        Deliberately optimistic-after-success and pessimistic-before: a single
        good answer proves the network path, and zero good answers with at
        least one attempt proves nothing about the data.
        """
        return self.successes > 0

    @property
    def attempted(self) -> bool:
        return self.attempts > 0

    def as_dict(self) -> dict:
        return {
            "service": self.name,
            "attempted": self.attempted,
            "reachable": self.reachable,
            "attempts": self.attempts,
            "successes": self.successes,
            "failures": self.failures,
            "last_error": self.last_error[:200],
        }


class _Attempt:
    def __init__(self, state: ServiceState) -> None:
        self._state = state
        self._done = False

    def succeeded(self) -> None:
        if not self._done:
            self._state.successes += 1
            self._done = True

    def failed(self, error: str = "") -> None:
        if not self._done:
            self._state.failures += 1
            if error:
                self._state.last_error = error
            self._done = True


class LookupStatus:
    """Thread-safe tally of external-service availability for one run."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._services: dict[str, ServiceState] = {}

    def _state(self, name: str) -> ServiceState:
        with self._lock:
            if name not in self._services:
                self._services[name] = ServiceState(name=name)
            return self._services[name]

    @contextmanager
    def attempt(self, name: str):
        state = self._state(name)
        with self._lock:
            state.attempts += 1
        handle = _Attempt(state)
        try:
            yield handle
        except Exception as exc:  # noqa: BLE001 — caller decides how to report
            handle.failed(f"{type(exc).__name__}: {exc}")
            raise
        finally:
            handle.failed()  # no-op if succeeded() or failed() was already called

    def reachable(self, name: str) -> bool:
        return self._state(name).reachable

    def attempted(self, name: str) -> bool:
        return self._state(name).attempted

    def offline_services(self) -> list[str]:
        """Services that were tried and never answered."""
        with self._lock:
            return sorted(
                s.name for s in self._services.values()
                if s.attempted and not s.reachable
            )

    def report(self) -> list[dict]:
        with self._lock:
            return [s.as_dict() for s in sorted(self._services.values(), key=lambda s: s.name)]

    def reset(self) -> None:
        with self._lock:
            self._services.clear()

    def summary_line(self) -> str:
        offline = self.offline_services()
        if not offline:
            with self._lock:
                used = sorted(s.name for s in self._services.values() if s.reachable)
            if not used:
                return "No external lookups were needed for this paper."
            return "External authorities consulted: " + ", ".join(used) + "."
        return (
            "Could not reach " + ", ".join(offline) + ". "
            "Checks that depend on them are reported as NOT CHECKED, not as problems."
        )


STATUS = LookupStatus()

# Human-readable names used in reports.
SERVICE_LABELS = {
    "crossref": "Crossref",
    "doi.org": "doi.org resolver",
    "jacow-refdb": "refs.jacow.org",
    "ltwa": "ISSN LTWA abbreviation list",
    "datacite": "DataCite",
    "llm": "local language model",
}


def label(service: str) -> str:
    return SERVICE_LABELS.get(service, service)
