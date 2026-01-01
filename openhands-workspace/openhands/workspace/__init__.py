"""OpenHands Workspace - Docker and container-based workspace implementations."""

from typing import TYPE_CHECKING

from openhands.sdk.workspace import PlatformType, TargetType

from .apptainer import ApptainerWorkspace
from .cloud import OpenHandsCloudWorkspace
from .docker import DockerWorkspace
from .remote_api import APIRemoteWorkspace


if TYPE_CHECKING:
    from .daytona import DaytonaWorkspace
    from .docker import DockerDevWorkspace

__all__ = [
    "APIRemoteWorkspace",
    "ApptainerWorkspace",
    "DaytonaWorkspace",
    "DockerDevWorkspace",
    "DockerWorkspace",
    "OpenHandsCloudWorkspace",
    "PlatformType",
    "TargetType",
]


def __getattr__(name: str):
    if name == "DockerDevWorkspace":
        from .docker import DockerDevWorkspace

        return DockerDevWorkspace

    if name == "DaytonaWorkspace":
        from .daytona import DaytonaWorkspace

        return DaytonaWorkspace

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
