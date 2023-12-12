import os
from pathlib import Path
from shutil import which
from typing import TypeVar

from psutil import Process

from ._exceptions import EnvironmentVariableError, ShellResolutionError


# TODO @adamhl8: test if executable is a shell, if not default to bash  # noqa: TD003, FIX002
def get_parent_shell_path() -> Path:
    """Return the full path of parent process/shell.

    This is used when X is called without explicitly passing in a shell.
    That way commands are executed using the same shell that invoked the script.
    """
    try:
        return Path(Process().parent().exe()).resolve(strict=True)
    except Exception as e:  # noqa: BLE001
        message = "An error occurred when trying to get the path of the parent shell."
        raise ShellResolutionError(message) from e


def resolve_shell_path(shell: str) -> Path:
    """Return the full path of a given path or executable name. e.g. '/bin/bash' or 'bash'.

    This is used when X is passed an argument for shell.
    """
    which_shell = which(shell, os.F_OK)
    if which_shell is None:
        message = f'Unable to resolve the path to shell "{shell}". It does not exist or it is not on your PATH.'
        raise ShellResolutionError(message)
    if not os.access(which_shell, os.X_OK):
        message = f'The file at "{which_shell}" is not executable.'
        raise ShellResolutionError(message)
    return Path(which_shell).resolve(strict=True)


Option = TypeVar("Option")


def resolve_option(option_arg: Option | None, env_var_value: Option | None, *, default: Option) -> Option:
    """Try to resolve an option: passed in value -> environment variable -> default.

    If option_arg is not None (something was passed in), return that value.
    If None, return the value of the related environment variable. Otherwise, fallback to the default value.
    """
    if option_arg is not None:
        return option_arg

    if env_var_value is not None:
        return env_var_value

    return default


class Env:
    """Helper class for resolving environment variables."""

    @staticmethod
    def get_bool(env_var: str) -> bool | None:
        value = os.getenv(env_var)
        if value is None:
            return None
        if value.title() == "True":
            return True
        if value.title() == "False":
            return False

        message = f'Received invalid value for environment variable {env_var}: "{value}"\nExpected "True" or "False" (case-insensitive).'  # noqa: E501
        raise EnvironmentVariableError(message)

    @staticmethod
    def get_str(env_var: str) -> str | None:
        return os.getenv(env_var)
