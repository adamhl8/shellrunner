"""shellrunner package."""

from ._exceptions import ShellCommandError, ShellCommandResult, ShellResolutionError, ShellRunnerError
from ._shellrunner import run as X  # noqa: N812

__all__ = [
    "X",
    "ShellCommandResult",
    "ShellCommandError",
    "ShellResolutionError",
    "ShellRunnerError",
]
