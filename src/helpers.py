import os
import subprocess
from pathlib import Path
from shutil import which
from typing import NamedTuple, TypeVar


class PipelineError(ChildProcessError):
    pass


class EnvironmentVariableError(ValueError):
    pass


class ResultTuple(NamedTuple):
    out: str
    status: int | list[int]


# Returns the full path of parent process/shell. That way commands are executed using the same shell that invoked this script.
def get_parent_shell_path() -> Path:
    try:
        ppid = os.getppid()
        path = subprocess.run(
            ["readlink", f"/proc/{ppid}/exe"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
    except:
        print("An error occured when trying to get the path of the parent shell:")
        raise
    else:
        return Path(path).resolve(strict=True)


# Returns the full path of a given path or executable name. e.g. "/bin/bash" or "bash"
def resolve_shell_path(shell: str) -> Path:
    which_shell = which(shell, os.X_OK)
    if which_shell is None:
        message = f'Unable to resolve the path to the executable: "{shell}". It is either not on your PATH or the specified file is not executable.'
        raise FileNotFoundError(message)
    return Path(which_shell).resolve(strict=True)


Option = TypeVar("Option", str, bool)


# If option_arg is not None (something was passed in), return that value. If None, return the value of the related environment variable. Otherwise, fallback to the default value.
def resolve_option(option_arg: Option | None, env_var_value: Option | None, *, default: Option) -> Option:
    if option_arg is not None:
        return option_arg

    if env_var_value is not None:
        return env_var_value

    return default


# Helper class for resolving environment variables.
class Env:
    @staticmethod
    def get_bool(env_var: str) -> bool | None:
        value = os.getenv(env_var)
        if value is None:
            return None
        if value.title() == "True":
            return True
        if value.title() == "False":
            return False

        message = f'Received invalid value for environment variable {env_var}: "{value}"\nExpected "True" or "False" (case-insensitive).'
        raise EnvironmentVariableError(message)

    @staticmethod
    def get_str(env_var: str) -> str | None:
        return os.getenv(env_var)