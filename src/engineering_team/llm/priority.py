"""Deterministic per-role provider ordering for CLOUD_FIRST/LOCAL_FIRST/etc."""

from dataclasses import dataclass
from typing import Any

from engineering_team.contracts.enums import ModelPriority


@dataclass(frozen=True)
class RuntimeOrder:
    primary: Any | None
    primary_is_cloud: bool
    fallback: Any | None
    fallback_is_cloud: bool


def resolve_runtime_order(
    priority: str | ModelPriority, local_runtime: Any | None, cloud_runtime: Any | None
) -> RuntimeOrder:
    """Return the (primary, fallback) runtime pair for the configured strategy.

    LOCAL_ONLY/CLOUD_ONLY never construct a fallback, matching the requirement
    that those modes never call the other provider under any circumstance. When
    only one runtime object is actually wired in (the other constructor argument
    was never provided), that runtime degrades gracefully to sole primary with
    no fallback rather than leaving the role uninvoked.
    """
    resolved = ModelPriority(priority)
    if resolved is ModelPriority.LOCAL_ONLY:
        return RuntimeOrder(local_runtime, False, None, False)
    if resolved is ModelPriority.CLOUD_ONLY:
        return RuntimeOrder(cloud_runtime, True, None, False)
    if resolved is ModelPriority.LOCAL_FIRST:
        ordered = [(local_runtime, False), (cloud_runtime, True)]
    else:
        ordered = [(cloud_runtime, True), (local_runtime, False)]
    available = [pair for pair in ordered if pair[0] is not None]
    if not available:
        return RuntimeOrder(None, False, None, False)
    primary, primary_is_cloud = available[0]
    fallback, fallback_is_cloud = available[1] if len(available) > 1 else (None, False)
    return RuntimeOrder(primary, primary_is_cloud, fallback, fallback_is_cloud)
