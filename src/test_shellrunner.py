#!/usr/bin/env python

import os
from pathlib import Path
from shutil import which
from typing import NamedTuple

import pytest
from psutil import Process
from shellrunner import PipelineError, X


class ShellInfo(NamedTuple):
    path: str
    name: str


@pytest.fixture()
def child_process_error_message():
    return "Command exited with non-zero status:"


@pytest.fixture()
def pipeline_error_message():
    return "Pipeline exited with non-zero status:"


# This code is separated from the parent_shell fixture so we can call it separately if needed.
def get_parent_shell_info():
    shell_path = Process().parent().exe()
    shell_path = Path(shell_path).resolve(strict=True)

    # If pytest is invoked via pdm, the parent process will be python, not the shell, so we fallback to bash.
    if shell_path.name.startswith("python"):
        return ShellInfo("/bin/bash", "bash")
    return ShellInfo(f"{shell_path}", shell_path.name)


# This fixture provides the path and name of the invoking shell. Primarily so this file doesn't have to be invoked by a particular shell.
@pytest.fixture(scope="session")
def parent_shell():
    return get_parent_shell_info()


# Set of shells that each test in TestCommands will be invoked with, including the shell that invoked pytest.
shells = {"bash", "zsh", "fish", "sh", f"{get_parent_shell_info().name}"}

# bash, zsh, fish, and sh need to be installed to run these tests.
for shell in shells:
    which_shell = which(shell, os.X_OK)
    if which_shell is None:
        message = f'Unable to resolve the path to the executable: "{shell}". It is either not on your PATH or the specified file is not executable.'
        raise FileNotFoundError(message)


# When using sh (or any other shell without $PIPESTATUS), we must treat pipelines as a single command when it comes to their exit status.
# Which means that sh will never raise a PipelineError.
@pytest.mark.parametrize("shell", shells)
class TestCommands:
    def test_single_command(self, shell: str):
        result = X("echo test", shell=shell)
        assert result.output == "test"
        assert result.status == 0

    def test_single_command_error(self, shell: str, child_process_error_message: str):
        with pytest.raises(ChildProcessError) as cm:
            X("false", shell=shell)
        assert str(cm.value).startswith(child_process_error_message)

    def test_unknown_command_raises_error(self, shell: str, child_process_error_message: str):
        with pytest.raises(ChildProcessError) as cm:
            X("foo", shell=shell)
        assert str(cm.value).startswith(child_process_error_message)

    def test_pipeline(self, shell: str):
        result = X("echo test | grep test", shell=shell)
        assert result.output == "test"
        if shell == "sh":
            assert result.status == 0
        else:
            assert result.status == [0, 0]

    def test_pipeline_error(self, shell: str, pipeline_error_message: str, child_process_error_message: str):
        if shell == "sh":
            with pytest.raises(ChildProcessError) as cm:
                X("true | true | false", shell=shell)
            assert str(cm.value).startswith(child_process_error_message)
        else:
            with pytest.raises(PipelineError) as cm:
                X("true | true | false", shell=shell)
            assert str(cm.value).startswith(pipeline_error_message)

    # fish does not execute a pipeline at all if any command is unknown, so we only get one exit status
    def test_pipeline_with_unknown_command_raises_error(
        self,
        shell: str,
        pipeline_error_message: str,
        child_process_error_message: str,
    ):
        if shell == "sh" or shell == "fish":
            with pytest.raises(ChildProcessError) as cm:
                X("true | foo", shell=shell)
            assert str(cm.value).startswith(child_process_error_message)
        else:
            with pytest.raises(PipelineError) as cm:
                X("true | foo", shell=shell)
            assert str(cm.value).startswith(pipeline_error_message)

    def test_command_list(self, shell: str):
        result = X(["echo test", "echo test"], shell=shell)
        assert result.output == "test\n\ntest"
        assert result.status == 0

    def test_command_list_error(self, shell: str, child_process_error_message: str):
        with pytest.raises(ChildProcessError) as cm:
            X(["echo test", "false"], shell=shell)
        assert str(cm.value).startswith(child_process_error_message)

    def test_command_list_maintains_environment(self, shell: str):
        result = X(["cd /", "pwd"], shell=shell)
        assert result.output == "/"
        assert result.status == 0

    def test_check_false_does_not_raise_error(self, shell: str):
        result = X("false", shell=shell, check=False)
        assert result.output == ""
        assert result.status == 1

    def test_check_false_does_not_stop_execution(self, shell: str):
        result = X(["false", "echo test"], shell=shell, check=False)
        assert result.output == "test"
        assert result.status == 0

    def test_pipefail_false_does_not_raise_error(self, shell: str):
        result = X("true | false | true", shell=shell, pipefail=False)
        assert result.output == ""
        if shell == "sh":
            assert result.status == 0
        else:
            assert result.status == [0, 1, 0]

    # Consistent with bash: set -e
    def test_pipefail_false_raises_error_if_last_command_errors(self, shell: str, child_process_error_message: str):
        with pytest.raises(ChildProcessError) as cm:
            X("true | true | false", shell=shell, pipefail=False)
        assert str(cm.value).startswith(child_process_error_message)

    def test_check_false_pipefail_false(self, shell: str):
        result = X("false", shell=shell, check=False, pipefail=False)
        assert result.output == ""
        assert result.status == 1

        result = X("true | false | false", shell=shell, check=False, pipefail=False)
        assert result.output == ""
        if shell == "sh":
            assert result.status == 1
        else:
            assert result.status == [0, 1, 1]

    def test_quiet_true(self, shell: str, capsys: pytest.CaptureFixture[str]):
        result = X("echo test", shell=shell, quiet=True)
        assert result.output == "test"
        assert result.status == 0
        captured = capsys.readouterr()
        assert captured.out == "Executing: echo test\n"

    def test_print_commands_false(self, shell: str, capsys: pytest.CaptureFixture[str]):
        result = X("echo test", shell=shell, print_commands=False)
        assert result.output == "test"
        assert result.status == 0
        captured = capsys.readouterr()
        assert captured.out == "test\n\n"

    def test_quiet_true_print_commands_false(self, shell: str, capsys: pytest.CaptureFixture[str]):
        result = X("echo test", shell=shell, quiet=True, print_commands=False)
        assert result.output == "test"
        assert result.status == 0
        captured = capsys.readouterr()
        assert captured.out == ""


class TestShellResolution:
    def test_resolve_shell_from_path(self, parent_shell: ShellInfo):
        result = X("echo test", shell=parent_shell.path)
        assert result.output == "test"
        assert result.status == 0

    def test_resolve_shell_from_name(self, parent_shell: ShellInfo):
        result = X("echo test", shell=parent_shell.name)
        assert result.output == "test"
        assert result.status == 0

    def test_invalid_shell_path_raises_error(self):
        with pytest.raises(FileNotFoundError):
            X("echo test", shell="/invalid/shell/path")

    def test_invalid_shell_name_raises_error(self):
        with pytest.raises(FileNotFoundError) as cm:
            X("echo test", shell="invalidshell")
        assert str(cm.value).startswith('Unable to resolve the path to the executable: "invalidshell".')

    def test_non_exectuable_file_raises_error(self, tmp_path: Path):
        file = tmp_path / "non_exectuable"
        file.write_text("temp")
        Path.chmod(file, 0o444)
        with pytest.raises(FileNotFoundError) as cm:
            X("echo test", shell=f"{file}")
        assert str(cm.value).startswith(f'Unable to resolve the path to the executable: "{file}".')

    def test_resolve_shell_path_from_environment_variable(
        self,
        monkeypatch: pytest.MonkeyPatch,
        parent_shell: ShellInfo,
    ):
        monkeypatch.setenv("SHELLRUNNER_SHELL", parent_shell.path)
        result = X("echo test")
        assert result.output == "test"
        assert result.status == 0

    def test_resolve_shell_name_from_environment_variable(
        self,
        monkeypatch: pytest.MonkeyPatch,
        parent_shell: ShellInfo,
    ):
        monkeypatch.setenv("SHELLRUNNER_SHELL", parent_shell.name)
        result = X("echo test")
        assert result.output == "test"
        assert result.status == 0

    def test_invalid_shell_path_in_environment_variable_raises_error(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SHELLRUNNER_SHELL", "/invalid/shell/path")
        with pytest.raises(FileNotFoundError):
            X("echo test")

    def test_invalid_shell_name_in_environment_variable_raises_error(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SHELLRUNNER_SHELL", "invalidshell")
        with pytest.raises(FileNotFoundError) as cm:
            X("echo test")
        assert str(cm.value).startswith('Unable to resolve the path to the executable: "invalidshell".')

    def test_shell_arg_takes_precedence_over_environment_variable(
        self,
        monkeypatch: pytest.MonkeyPatch,
        parent_shell: ShellInfo,
    ):
        monkeypatch.setenv("SHELLRUNNER_SHELL", "invalidshell")
        result = X("echo test", shell=parent_shell.path)
        assert result.output == "test"
        assert result.status == 0
