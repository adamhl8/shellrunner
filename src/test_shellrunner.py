import os
import re
from pathlib import Path
from shutil import which
from typing import NamedTuple

import pytest
from helpers import EnvironmentVariableError, ShellCommandError, ShellResolutionError, get_parent_shell_path
from shellrunner import X


class ShellInfo(NamedTuple):
    path: str
    name: str


@pytest.fixture()
def shell_command_error_message():
    return "Command exited with non-zero status:"


# This code is separated from the parent_shell fixture so we can call it separately if needed.
def get_parent_shell_info():
    shell_path = get_parent_shell_path()

    # If pytest is invoked via pdm, the parent process will be python, not the shell, so we fallback to bash.
    # Similarly, if pytest is invoked via VS Code, the parent process will be node.
    if shell_path.name.startswith("python") or shell_path.name.startswith("node"):
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

# ruff: noqa: PLR2004


# When using sh (or any other shell without PIPESTATUS), we will only ever receive a single exit status.
@pytest.mark.parametrize("shell", shells)
class TestCommands:
    def test_single_command(self, shell: str):
        result = X("echo test", shell=shell)
        assert result.out == "test"
        assert result.status == 0
        assert result.pipestatus == [0]

    def test_single_command_error(self, shell: str, shell_command_error_message: str):
        with pytest.raises(ShellCommandError) as cm:
            X("false", shell=shell)
        assert str(cm.value).startswith(shell_command_error_message)
        assert cm.value.out == ""
        assert cm.value.status == 1
        assert cm.value.pipestatus == [1]

    def test_unknown_command_raises_error(self, shell: str, shell_command_error_message: str):
        with pytest.raises(ShellCommandError) as cm:
            X("foo", shell=shell)
        assert str(cm.value).startswith(shell_command_error_message)
        assert cm.value.status == 127
        assert cm.value.pipestatus == [127]

    def test_pipeline(self, shell: str):
        result = X("echo test | grep test", shell=shell)
        assert result.out == "test"
        assert result.status == 0
        if shell == "sh":
            assert result.pipestatus == [0]
        else:
            assert result.pipestatus == [0, 0]

    def test_pipeline_error(self, shell: str, shell_command_error_message: str):
        # sh does not have PIPESTATUS so we shouldn't get an error if the non-zero exit was not the last command.
        if shell == "sh":
            result = X("false | echo test", shell=shell)
            assert result.out == "test"
            assert result.status == 0
            assert result.pipestatus == [0]
        else:
            with pytest.raises(ShellCommandError) as cm:
                X("false | echo test", shell=shell)
            assert str(cm.value).startswith(shell_command_error_message)
            assert cm.value.out == "test"
            assert cm.value.status == 1
            assert cm.value.pipestatus == [1, 0]

        # Test when only last command fails.
        with pytest.raises(ShellCommandError) as cm:
            X("true | false", shell=shell)
        assert str(cm.value).startswith(shell_command_error_message)
        assert cm.value.out == ""
        assert cm.value.status == 1
        if shell == "sh":
            assert cm.value.pipestatus == [1]
        else:
            assert cm.value.pipestatus == [0, 1]

    def test_status_equals_status_of_last_failing_command(self, shell: str, shell_command_error_message: str):
        if shell == "sh":
            result = X("bash -c 'exit 1' | bash -c 'exit 2' | echo test", shell=shell)
            assert result.out == "test"
            assert result.status == 0
            assert result.pipestatus == [0]
        else:
            with pytest.raises(ShellCommandError) as cm:
                X("bash -c 'exit 1' | bash -c 'exit 2' | echo test", shell=shell)
            assert str(cm.value).startswith(shell_command_error_message)
            assert cm.value.out == "test"
            assert cm.value.status == 2
            assert cm.value.pipestatus == [1, 2, 0]

    def test_pipeline_with_unknown_command_raises_error(self, shell: str, shell_command_error_message: str):
        with pytest.raises(ShellCommandError) as cm:
            X("true | foo", shell=shell)
        assert str(cm.value).startswith(shell_command_error_message)
        assert cm.value.status == 127
        # fish will not run a pipeline whatsoever if any command is unknown so we will only ever get one status.
        if shell == "sh" or shell == "fish":
            assert cm.value.pipestatus == [127]
        else:
            assert cm.value.pipestatus == [0, 127]

    def test_command_list(self, shell: str):
        result = X(["echo test", "echo test"], shell=shell)
        assert result.out == "test\ntest"
        assert result.status == 0
        assert result.pipestatus == [0]

    def test_command_list_status_is_of_last_command(self, shell: str):
        result = X(["echo test | grep test", "echo test"], shell=shell)
        assert result.out == "test\ntest"
        assert result.status == 0
        assert result.pipestatus == [0]

    def test_command_list_error(self, shell: str, shell_command_error_message: str):
        with pytest.raises(ShellCommandError) as cm:
            X(["echo test", "false"], shell=shell)
        assert str(cm.value).startswith(shell_command_error_message)
        assert cm.value.out == "test"
        assert cm.value.status == 1
        assert cm.value.pipestatus == [1]

    def test_command_list_maintains_environment(self, shell: str):
        result = X(["cd /", "pwd"], shell=shell)
        assert result.out == "/"
        assert result.status == 0
        assert result.pipestatus == [0]


@pytest.mark.parametrize("shell", shells)
class TestOptions:
    # The shell option is tested in the ShellResolution class.

    def test_check_false_does_not_raise_error(self, shell: str):
        result = X("false", shell=shell, check=False)
        assert result.out == ""
        assert result.status == 1
        assert result.pipestatus == [1]

    def test_check_false_with_pipeline_does_not_raise_error(self, shell: str):
        result = X("false | false", shell=shell, check=False)
        assert result.out == ""
        assert result.status == 1
        if shell == "sh":
            assert result.pipestatus == [1]
        else:
            assert result.pipestatus == [1, 1]

    def test_check_false_does_not_stop_execution(self, shell: str):
        result = X(["false", "echo test"], shell=shell, check=False)
        assert result.out == "test"
        assert result.status == 0
        assert result.pipestatus == [0]

    def test_show_output_false(self, shell: str, capsys: pytest.CaptureFixture[str]):
        result = X("echo test", shell=shell, show_output=False)
        assert result.out == "test"
        assert result.status == 0
        assert result.pipestatus == [0]
        captured = capsys.readouterr()
        assert captured.out == "Executing: echo test\n"

    def test_show_commands_false(self, shell: str, capsys: pytest.CaptureFixture[str]):
        result = X("echo test", shell=shell, show_commands=False)
        assert result.out == "test"
        assert result.status == 0
        assert result.pipestatus == [0]
        captured = capsys.readouterr()
        assert captured.out == "test\n"

    def test_show_output_false_show_commands_false(self, shell: str, capsys: pytest.CaptureFixture[str]):
        result = X("echo test", shell=shell, show_output=False, show_commands=False)
        assert result.out == "test"
        assert result.status == 0
        assert result.pipestatus == [0]
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_environment_variable_options(
        self,
        shell: str,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        monkeypatch.setenv("SHELLRUNNER_CHECK", "False")
        monkeypatch.setenv("SHELLRUNNER_SHOW_OUTPUT", "False")
        monkeypatch.setenv("SHELLRUNNER_SHOW_COMMANDS", "False")

        result = X("true | false | false", shell=shell)
        assert result.out == ""
        assert result.status == 1
        if shell == "sh":
            assert result.pipestatus == [1]
        else:
            assert result.pipestatus == [0, 1, 1]

        result = X("echo test", shell=shell)
        assert result.out == "test"
        assert result.status == 0
        assert result.pipestatus == [0]
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_args_take_precedence_over_environment_variables(
        self,
        shell: str,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        shell_command_error_message: str,
    ):
        monkeypatch.setenv("SHELLRUNNER_CHECK", "False")
        monkeypatch.setenv("SHELLRUNNER_SHOW_OUTPUT", "False")
        monkeypatch.setenv("SHELLRUNNER_SHOW_COMMANDS", "False")

        with pytest.raises(ShellCommandError) as cm:
            X("false", shell=shell, check=True)
        assert str(cm.value).startswith(shell_command_error_message)
        assert cm.value.out == ""
        assert cm.value.status == 1
        assert cm.value.pipestatus == [1]

        result = X("echo test", shell=shell, show_commands=True, show_output=True)
        assert result.out == "test"
        assert result.status == 0
        assert result.pipestatus == [0]
        captured = capsys.readouterr()
        assert captured.out == "Executing: echo test\ntest\n"

    def test_invalid_bool_value_for_environment_variable_raises_error(
        self,
        shell: str,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("SHELLRUNNER_CHECK", "foo")

        with pytest.raises(EnvironmentVariableError) as cm:
            X("false", shell=shell)
        assert (
            str(cm.value)
            == 'Received invalid value for environment variable SHELLRUNNER_CHECK: "foo"\nExpected "True" or "False" (case-insensitive).'
        )


class TestShellResolution:
    def test_resolve_shell_from_path(self, parent_shell: ShellInfo):
        result = X("echo test", shell=parent_shell.path)
        assert result.out == "test"
        assert result.status == 0
        assert result.pipestatus == [0]

    def test_resolve_shell_from_name(self, parent_shell: ShellInfo):
        result = X("echo test", shell=parent_shell.name)
        assert result.out == "test"
        assert result.status == 0
        assert result.pipestatus == [0]

    def test_invalid_shell_path_raises_error(self):
        with pytest.raises(ShellResolutionError):
            X("echo test", shell="/invalid/shell/path")

    def test_invalid_shell_name_raises_error(self):
        with pytest.raises(ShellResolutionError) as cm:
            X("echo test", shell="invalidshell")
        assert str(cm.value).startswith('Unable to resolve the path to the executable: "invalidshell".')

    def test_python_as_parent_process_raises_error(self):
        with pytest.raises(ShellResolutionError) as cm:
            X("echo test", shell="python")
        assert re.fullmatch("Process .+ is not a shell. Please provide a shell name or path.", str(cm.value))

    def test_non_exectuable_file_raises_error(self, tmp_path: Path):
        file = tmp_path / "non_exectuable"
        file.write_text("temp")
        Path.chmod(file, 0o444)
        with pytest.raises(ShellResolutionError) as cm:
            X("echo test", shell=f"{file}")
        assert str(cm.value).startswith(f'Unable to resolve the path to the executable: "{file}".')

    def test_resolve_shell_path_from_environment_variable(
        self,
        monkeypatch: pytest.MonkeyPatch,
        parent_shell: ShellInfo,
    ):
        monkeypatch.setenv("SHELLRUNNER_SHELL", parent_shell.path)
        result = X("echo test")
        assert result.out == "test"
        assert result.status == 0
        assert result.pipestatus == [0]

    def test_resolve_shell_name_from_environment_variable(
        self,
        monkeypatch: pytest.MonkeyPatch,
        parent_shell: ShellInfo,
    ):
        monkeypatch.setenv("SHELLRUNNER_SHELL", parent_shell.name)
        result = X("echo test")
        assert result.out == "test"
        assert result.status == 0
        assert result.pipestatus == [0]

    def test_invalid_shell_path_in_environment_variable_raises_error(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SHELLRUNNER_SHELL", "/invalid/shell/path")
        with pytest.raises(ShellResolutionError):
            X("echo test")

    def test_invalid_shell_name_in_environment_variable_raises_error(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SHELLRUNNER_SHELL", "invalidshell")
        with pytest.raises(ShellResolutionError) as cm:
            X("echo test")
        assert str(cm.value).startswith('Unable to resolve the path to the executable: "invalidshell".')

    def test_shell_arg_takes_precedence_over_environment_variable(
        self,
        monkeypatch: pytest.MonkeyPatch,
        parent_shell: ShellInfo,
    ):
        monkeypatch.setenv("SHELLRUNNER_SHELL", "invalidshell")
        result = X("echo test", shell=parent_shell.path)
        assert result.out == "test"
        assert result.status == 0
        assert result.pipestatus == [0]
