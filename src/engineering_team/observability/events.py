"""Sinks that receive RunEvents as a workflow run executes.

A sink never blocks or fails the run: implementations that talk to an
external system (Kafka in Phase 2) are expected to catch their own errors.
"""

from __future__ import annotations

from typing import Protocol

from engineering_team.contracts.models import RunEvent


class RunEventSink(Protocol):
    def emit(self, event: RunEvent) -> None: ...


class NullRunEventSink:
    """Default sink: discards every event. Used when no caller wants one."""

    def emit(self, event: RunEvent) -> None:
        return None


class ListRunEventSink:
    """In-memory sink for tests and for a single synchronous CLI run."""

    def __init__(self) -> None:
        self.events: list[RunEvent] = []

    def emit(self, event: RunEvent) -> None:
        self.events.append(event)
