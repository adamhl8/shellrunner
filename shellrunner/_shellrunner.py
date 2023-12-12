import subprocess
import sys
from inspect import cleandoc
from pathlib import Path
from typing import NamedTuple

from ._exceptions import ShellCommandError, ShellCommandResult, ShellResolutionError, ShellRunnerError
from ._utils import Env, get_parent_shell_path, resolve_option, resolve_shell_path

# ruff: noqa: T201


def run(
    command: str | list[str],
    *,
    shell: str | Path | None = None,
    check: bool | None = None,
    show_output: bool | None = None,
    show_command: bool | None = None,
) -> ShellCommandResult:
    """Execute a command or a list of commands using a shell.

    Args:
    ----
    command (str | list[str]): The command or list of commands to be executed by the shell.

    The following keyword arguments are all optional:
    shell (str | Path): The shell that will be used to execute the commands.
        Can be a name/path (str) or a pathlib Path (e.g. "bash", "/bin/bash").
        Defaults to the shell that invoked the script.
    check (bool): If True, an error will be thrown if a command exits with a non-zero status.
        Similar to bash's "set -e". Defaults to True.
    show_output (bool): If True, command output will be printed. Defaults to True.
    show_command (bool): If True, the current command will be printed before execution. Defaults to True.

    Returns:
    -------
    ShellCommandResult: The result of the shell command execution.

    Raises:
    ------
    ShellResolutionError: Raised if an error occurs when resolving the path to the shell.
    ShellCommandError: If check is True, this is raised if a command exits with a non-zero status.
    ShellRunnerError: Raised when an unexpected error occurs.
        Usually an execution error with this function, not necessarily the provided command.
    """
    options = _resolve_options(shell, check, show_output, show_command)
    shell, check, show_output, show_command = options

    # Ensure command_list is always a list
    command_list = command if isinstance(command, list) else [command]
    commands = _build_commands(command_list, options)

    # Print command_list rather than commands so we don't see the appended status_checks.
    if show_command:
        print(f"shellrunner: \033[33m{'; '.join(command_list)}\033[0m")

    output, pipestatus_list = _run_commands(commands, options)

    # If we don't receive any exit status, something went wrong.
    if not pipestatus_list:
        message = "Something went wrong. Failed to capture an exit status."
        raise ShellRunnerError(message)

    status = pipestatus_list[-1]
    # status is equal to the last failed command in a pipeline.
    for s in reversed(pipestatus_list):
        if s != 0:
            status = s
            break

    result = ShellCommandResult(output.rstrip(), status, pipestatus_list)

    if check:
        for status in pipestatus_list:
            if status != 0:
                message = f"Command exited with non-zero status: {pipestatus_list}"
                raise ShellCommandError(message, result)

    return result


class Options(NamedTuple):
    shell: Path
    check: bool
    show_output: bool
    show_command: bool


def _resolve_options(
    shell: str | Path | None = None,
    check: bool | None = None,
    show_output: bool | None = None,
    show_command: bool | None = None,
) -> Options:
    """Build Options with resolved values."""
    # We default each argument to None rather than the "real" defaults
    # so we can detect if the user actually passed something in.
    shell = resolve_option(shell, Env.get_str("SHELLRUNNER_SHELL"), default="")
    # If given a shell, resolve its path and run the commands with it instead of the invoking shell.
    shell = resolve_shell_path(str(shell)) if shell else get_parent_shell_path()
    # If for some reason python is the parent process (or if the user passes in python) we can't continue.
    # TODO @adamhl8: detect valid shell  # noqa: TD003, FIX002
    if shell.name.startswith("python"):
        message = f'Process "{shell.name}" is not a shell. Please provide a shell name or path.'
        raise ShellResolutionError(message)

    check = resolve_option(check, Env.get_bool("SHELLRUNNER_CHECK"), default=True)
    show_output = resolve_option(show_output, Env.get_bool("SHELLRUNNER_SHOW_OUTPUT"), default=True)
    show_command = resolve_option(show_command, Env.get_bool("SHELLRUNNER_SHOW_COMMAND"), default=True)
    return Options(shell, check, show_output, show_command)


def _build_commands(command_list: list[str], options: Options) -> str:
    """Build the command string that will be passed to the shell."""
    """
    The only way to reliably stop executing commands on an error is to exit from the shell itself.
    Killing the subprocess does not happen nearly fast enough.
    To do this, we append a command for each command that is passed in.
    Ultimately, we need to get PIPESTATUS, process it, and exit based on that. PIPESTATUS looks like: "0 1 0".
    We don't need to also get $?/$status because PIPESTATUS gives the status of single command anyway.
    Rather than write a separate script for each shell to process PIPESTATUS
    (e.g. bash would require a different script than fish), we can pass PIPESTATUS into a python script.
    We execute this python script by passing it to the parent python executable (sys.executable) via the -c flag.
    The following python code (status_check) takes in PIPESTATUS, prints it (so we can capture it from stdout later on),
    loops through each status, and exits (with a non-zero status if there is one).
    """
    status_check = r"""
        import sys
        pipestatus = sys.argv[1]
        print('\u2f4c' + f' : {pipestatus} : ' + '\u2f8f', end='')
        for status in [int(x) for x in pipestatus.split()]:
            if status != 0: sys.exit(status)
    """
    """
    We use "⽌" and "⾏" as markers (that we'll likely never come across in the wild) to detect when
    a given command has finished. That way we can separately capture PIPESTATUS from stdout (and not print it).
    The markers are Japanese radicals rather than full Kanji, so they do not appear in "normal" Japanese text.
    e.g. we use ⾏ (U+2F8F) instead of 行 (U+884C).
    We read stdout on each character rather than by line, so we have to detect on a single character.
    ^ See the subprocess while loop.
    In the above print statement, we use unicode escapes to "hide" the characters from the shell.
    '\u2f4c' == ⽌ | '\u2f8f' == ⾏
    This is to prevent errors that would arise if the shell reprints the command. For example, when fish receives an
    unknown command in a pipeline, it reprints the entire command to point out where the error occurred.
    If we used the actual characters in that case, we would fail to correctly capture pipestatus because we would be
    capturing the literal command sent to the shell, not pipestatus as printed from the code.
    """

    # Remove unnecessary whitespace.
    status_check = cleandoc(status_check)

    # "Pure" POSIX shells do not have PIPESTATUS so only the exit status of the last command in a pipeline is available.
    status_var = r"$?"
    pipestatus_var = status_var
    if options.shell.name == "bash":
        pipestatus_var = r"${PIPESTATUS[*]}"
    if options.shell.name in ("zsh", "fish"):
        status_var = r"$status"
        pipestatus_var = r"$pipestatus"

    # If check argument is false, we won't exit after a non-zero exit status.
    # When run in shell that masks pipeline errors (e.g. bash),
    # status_var will be 0 even though an error may have occurred in a pipeline.
    # Ultimately this doesn't matter because we don't care about the exit status of the shell itself.
    exit_command = f' || exit "{status_var}"' if options.check else ""

    # This command is appended after each passed in command.
    # If status_check exits with a non-zero status, we exit the shell.
    status_command = f'{sys.executable} -c "{status_check}" "{pipestatus_var}"{exit_command}'

    # This will be command_list but with status_command appended.
    commands = command_list.copy()

    for i in range(1, len(command_list) * 2, 2):
        commands.insert(i, status_command)

    # Say the user passes in "echo hello".
    # In the end, the commands variable looks something like this:
    # echo hello; /path/to/python -c "status_check_code_here" $pipestatus || exit $status
    return "; ".join(commands)


def _run_commands(commands: str, options: Options) -> tuple[str, list[int]]:
    """Execute the provided commands string."""
    output = ""
    pipestatus = ""
    pipestatus_list = []

    # By using the Popen context manager via with, standard file descriptors are automatically closed.
    with subprocess.Popen(
        commands,
        shell=True,  # noqa: S602
        executable=options.shell,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ) as process:
        if process.stdout is None:
            message = "process.stdout is None"
            raise ShellRunnerError(message)

        capture_output = True
        # If we are still receiving output or poll() is None, we know the command is still running.
        # We must use stdout.read(1) rather than readline() in order to properly print commands
        # that prompt the user for input.
        # We must also forcibly flush the stream in the print statement for the same reason.
        while (out := process.stdout.read(1)) or process.poll() is None:
            # If we detect our marker, we know we are done with the previous command and have printed PIPESTATUS.
            # Capture stdout to pipestatus instead.
            if out.startswith("⽌"):
                capture_output = False
            if capture_output and out:
                # Probably unnecessary? Not sure if this flushes the same stream that we print to,
                # or if this flushes the stream that is "internal" to the spawned shell.
                process.stdout.flush()

                if options.show_output:
                    # We would be adding extra \n to the output if we don't specify end="".
                    print(out, end="", flush=True)
                output += out
            else:
                pipestatus += out

            # If we detect our marker, we know we've finished capturing PIPESTATUS and can start printing output again.
            if out.startswith("⾏"):
                if pipestatus:
                    pipestatus = pipestatus.split(" : ")[1]
                    # Convert pipestatus to a list of ints: '0 1 0' -> [0, 1, 0]
                    pipestatus_list = [int(x) for x in pipestatus.split()]
                capture_output = True

    return output, pipestatus_list
