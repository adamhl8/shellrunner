from typing import NamedTuple


class ShellCommandResult(NamedTuple):
    out: str
    status: int
    pipestatus: list[int]


class ShellRunnerError(RuntimeError):
    pass


class ShellCommandError(ShellRunnerError):
    def __init__(self, message: str, result: ShellCommandResult):
        super().__init__(message)
        self.out = result.out
        self.status = result.status
        self.pipestatus = result.pipestatus


class ShellResolutionError(ShellRunnerError):
    pass


class EnvironmentVariableError(ShellRunnerError):
    pass
