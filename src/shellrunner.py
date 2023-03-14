import inspect
import os
import subprocess
import sys
from pathlib import Path
from shutil import which
from typing import NamedTuple

from psutil import Process


class PipelineError(ChildProcessError):
    pass


class ResultTuple(NamedTuple):
    out: str
    status: int | list[int]


# Returns the full path of parent process/shell. That way commands are executed using the same shell that invoked this script.
def _get_parent_shell_path() -> Path:
    try:
        return Path(Process().parent().exe()).resolve(strict=True)
    except:
        print("An error occured when trying to get the path of the parent shell:")
        raise


# We only need to do this once (on import) since it should never change between calls of X.
parent_shell_path = _get_parent_shell_path()


# Returns the full path of a given path or executable name. e.g. "/bin/bash" or "bash"
def _resolve_shell_path(shell: str) -> Path:
    which_shell = which(shell, os.X_OK)
    if which_shell is None:
        message = f'Unable to resolve the path to the executable: "{shell}". It is either not on your PATH or the specified file is not executable.'
        raise FileNotFoundError(message)
    return Path(which_shell).resolve(strict=True)


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
        raise ValueError(message)

    @staticmethod
    def get_str(env_var: str) -> str | None:
        return os.getenv(env_var)


def X(  # noqa: N802
    command: str | list[str],
    *,
    shell: str | None = None,
    check: bool | None = None,
    pipefail: bool | None = None,
    show_output: bool | None = None,
    show_commands: bool | None = None,
) -> ResultTuple:
    shell = shell if shell is not None else Env.get_str("SHELLRUNNER_SHELL") or ""
    # If given a shell, resolve its path and run the commands with it instead of the invoking shell.
    shell_path = _resolve_shell_path(shell) if shell else parent_shell_path
    check = check if check is not None else Env.get_bool("SHELLRUNNER_CHECK") or True
    pipefail = pipefail if pipefail is not None else Env.get_bool("SHELLRUNNER_PIPEFAIL") or True
    show_output = show_output if show_output is not None else Env.get_bool("SHELLRUNNER_SHOW_OUTPUT") or True
    show_commands = show_commands if show_commands is not None else Env.get_bool("SHELLRUNNER_SHOW_COMMANDS") or True

    shell_name = shell_path.name

    # If a single command is passed in, put it in a list to simplify processing later on.
    if isinstance(command, str):
        command = [command]
    command_list = command  # Rename

    # The only way to reliably stop executing commands on an error is to exit from the shell itself. Killing the subprocess does not happen nearly fast enough.
    # To do this, we append a command for each command that is passed in. Ultimately, we need to get $PIPESTATUS, process it, and exit based on that. $PIPESTATUS looks like: "0 1 0".
    # We don't need to also get $?/$status because $PIPESTATUS gives the status of single command anyway.
    # Rather than write a separate script for each shell to process $PIPESTATUS (e.g. bash would requier a different script than fish), we can pass $PIPESTATUS into a python script.
    # We execute this python script by passing it to the parent python executable (sys.executable) via the -c flag.
    # The following python code (status_check) takes in $PIPESTATUS, prints it (so we can capture it from stdout later on), loops through each status, and exits (with a non-zero status if there is one).
    status_check = r"""
        import sys
        pipestatus = sys.argv[1]
        print(b'\\u2f4c'.decode('unicode_escape') + f' : {pipestatus} : ' + b'\\u2f8f'.decode('unicode_escape'), end='')
        for status in [int(x) for x in pipestatus.split()]:
            if status != 0: sys.exit(status)
    """
    # We use "⽌" and "⾏" as markers (that we'll likely never come across in the wild) to detect when a given command has finished. That way we can separately capture $PIPESTATUS from stdout (and not print it).
    # The markers are Japanese radicals rather than full Kanji, so they do not appear in "normal" Japanese text. e.g. we use ⾏ (U+2F8F) instead of 行 (U+884C).
    # We read stdout on each character rather than by line, so we have to detect on a single character. See the subprocess while loop.
    # In the above print statement, we use unicode escapes to "hide" the characters from the shell and only convert them back when the code is actually executed. '\u2f4c' == ⽌ | '\u2f8f' == ⾏
    # This is to prevent errors that would arise if the shell reprints the command. For example, when fish receives an unknown command in a pipeline, it reprints the entire command to point out where the error occured.
    # If we used the actual characters in that case, we would fail to correctly capture pipestatus because we would be capturing the literal command sent to the shell, not pipestatus as printed from the code.

    # Remove unnecessary whitespace.
    status_check = inspect.cleandoc(status_check)

    # Default to sh. "Pure" POSIX shells do not have $PIPESTATUS so only the exit status of the last command in a pipeline is available.
    pipestatus_var = r"$?"
    status_var = r"$?"
    if shell_name == "bash":
        pipestatus_var = r"${PIPESTATUS[*]}"
    if shell_name == "zsh" or shell_name == "fish":
        pipestatus_var = r"$pipestatus"
        status_var = r"$status"

    # If check argument is false, we won't exit after a non-zero exit status.
    exit_command = f' || exit "{status_var}"' if check else ""

    # This command is appended after each passed in command. If status_check exits with a non-zero status, we exit the shell.
    status_command = f'{sys.executable} -c "{status_check}" "{pipestatus_var}"{exit_command}'

    # This will be command_list but with status_command appended.
    commands = command_list.copy()

    for i in range(1, len(command_list) * 2, 2):
        commands.insert(i, status_command)

    commands = "; ".join(commands)
    # Say the user passes in "echo hello". In the end, the commands variable looks something like this: echo hello; /path/to/python -c "status_check_code_here" $pipestatus || exit $status

    output = ""
    pipestatus = ""
    status_list = []

    # Print command_list rather than commands so we don't see the appended status_checks.
    if show_commands:
        print(f"Executing: {'; '.join(command_list)}")

    # By using the Popen context manager via with, standard file descriptors are automatically closed.
    with subprocess.Popen(
        commands,
        shell=True,
        executable=shell_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ) as process:
        if process.stdout is None:
            message = "process.stdout is None"
            raise RuntimeError(message)

        capture_output = True
        # If we are still receving output or poll() is None, we know the command is still running.
        # We must use stdout.read(1) rather than readline() in order to properly print commands that prompt the user for input. We must also forcibly flush the stream in the print statement for the same reason.
        while (out := process.stdout.read(1)) or process.poll() is None:
            # If we detect our marker, we know we are done with the previous command and have printed $PIPESTATUS. Capture stdout to pipestatus instead.
            if out.startswith("⽌"):
                capture_output = False
            if capture_output and out:
                process.stdout.flush()  # Probably unnecessary? Not sure if this flushes the same stream that we print to, or if this flushes the stream that is "internal" to the spawned shell.
                if show_output:
                    # We would be adding extra \n to the output if we don't specify end="".
                    print(out, end="", flush=True)
                output += out
            else:
                pipestatus += out

            # If we detect our marker, we know we have finished capturing $PIPESTATUS and can start printing output again.
            if out.startswith("⾏"):
                if pipestatus:
                    pipestatus = pipestatus.split(" : ")[1]
                    # Convert pipestatus to a list of ints: '0 1 0' -> [0, 1, 0]
                    status_list = [int(x) for x in pipestatus.split()]
                capture_output = True

    # Only check for a pipeline error if there is more than 1 status.
    command_was_pipeline = len(status_list) > 1
    if pipefail and command_was_pipeline:
        for status in status_list:
            if status != 0:
                message = f"Pipeline exited with non-zero status: {status_list}"
                raise PipelineError(message)

    # Exit status of a given command is always the last status of a pipeline. Equivalent to $?/$status.
    try:
        status = status_list[-1]
    except IndexError:
        print("Unable to get exit status of command.")
        raise

    if check and status != 0:
        message = f"Command exited with non-zero status: {status}"
        raise ChildProcessError(message)

    return ResultTuple(output, status_list if command_was_pipeline else status)
