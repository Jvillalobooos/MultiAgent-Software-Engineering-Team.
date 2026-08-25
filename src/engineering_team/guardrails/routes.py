from collections.abc import Collection

from engineering_team.contracts.enums import RouteTarget


def validate_route(target: RouteTarget, allowed: Collection[RouteTarget]) -> RouteTarget:
    if target not in allowed:
        raise ValueError(f"route {target} is not allowed")
    return target
