import subprocess
import sys
from inspect import cleandoc

from ._exceptions import ShellCommandError, ShellCommandResult, ShellResolutionError, ShellRunnerError
from ._utils import (
    Env,
    get_parent_shell_path,
    resolve_option,
    resolve_shell_path,
)

# Parameters:
# command - String or list of strings that will be executed by the shell.
# shell (Optional) - Shell that will be used to execute the commands. Can be a path or simply the name (e.g. "/bin/bash", "bash"). | Default is the shell that invoked this script.
# check (Optional) - If True, an error will be thrown if a command exits with a non-zero status. Equivalent to bash's "set -e". | Default is True
# show_output (Optional) - If True, command output will be printed. | Default is True
# show_commands (Optional) - If True, the current command will be printed before execution. | Default is True


def run(
    command: str | list[str],
    *,
    shell: str | None = None,
    check: bool | None = None,
    show_output: bool | None = None,
    show_commands: bool | None = None,
) -> ShellCommandResult:
    # We default each argument to None rather than the "real" defaults so we can detect if the user actually passed something in.
    # Passed in arguments take precedence over the related environment variable.
    shell = resolve_option(shell, Env.get_str("SHELLRUNNER_SHELL"), default="")
    # If given a shell, resolve its path and run the commands with it instead of the invoking shell.
    shell_path = resolve_shell_path(shell) if shell else get_parent_shell_path()
    shell_name = shell_path.name
    # If for some reason python is the parent process (or if the user passes in python) we can't continue.
    if shell_name.startswith("python"):
        message = f'Process "{shell_name}" is not a shell. Please provide a shell name or path.'
        raise ShellResolutionError(message)

    check = resolve_option(check, Env.get_bool("SHELLRUNNER_CHECK"), default=True)
    show_output = resolve_option(show_output, Env.get_bool("SHELLRUNNER_SHOW_OUTPUT"), default=True)
    show_commands = resolve_option(show_commands, Env.get_bool("SHELLRUNNER_SHOW_COMMANDS"), default=True)

    # If a single command is passed in, put it in a list to simplify processing later on.
    if isinstance(command, str):
        command = [command]
    command_list = command  # Rename

    # The only way to reliably stop executing commands on an error is to exit from the shell itself. Killing the subprocess does not happen nearly fast enough.
    # To do this, we append a command for each command that is passed in. Ultimately, we need to get PIPESTATUS, process it, and exit based on that. PIPESTATUS looks like: "0 1 0".
    # We don't need to also get $?/$status because PIPESTATUS gives the status of single command anyway.
    # Rather than write a separate script for each shell to process PIPESTATUS (e.g. bash would require a different script than fish), we can pass PIPESTATUS into a python script.
    # We execute this python script by passing it to the parent python executable (sys.executable) via the -c flag.
    # The following python code (status_check) takes in PIPESTATUS, prints it (so we can capture it from stdout later on), loops through each status, and exits (with a non-zero status if there is one).
    status_check = r"""
        import sys
        pipestatus = sys.argv[1]
        print('\u2f4c' + f' : {pipestatus} : ' + '\u2f8f', end='')
        for status in [int(x) for x in pipestatus.split()]:
            if status != 0: sys.exit(status)
    """
    # We use "⽌" and "⾏" as markers (that we'll likely never come across in the wild) to detect when a given command has finished. That way we can separately capture PIPESTATUS from stdout (and not print it).
    # The markers are Japanese radicals rather than full Kanji, so they do not appear in "normal" Japanese text. e.g. we use ⾏ (U+2F8F) instead of 行 (U+884C).
    # We read stdout on each character rather than by line, so we have to detect on a single character. See the subprocess while loop.
    # In the above print statement, we use unicode escapes to "hide" the characters from the shell and only convert them back when the code is actually executed. '\u2f4c' == ⽌ | '\u2f8f' == ⾏
    # This is to prevent errors that would arise if the shell reprints the command. For example, when fish receives an unknown command in a pipeline, it reprints the entire command to point out where the error occured.
    # If we used the actual characters in that case, we would fail to correctly capture pipestatus because we would be capturing the literal command sent to the shell, not pipestatus as printed from the code.

    # Remove unnecessary whitespace.
    status_check = cleandoc(status_check)

    # Default to sh. "Pure" POSIX shells do not have PIPESTATUS so only the exit status of the last command in a pipeline is available.
    status_var = r"$?"
    pipestatus_var = status_var
    if shell_name == "bash":
        pipestatus_var = r"${PIPESTATUS[*]}"
    if shell_name in ("zsh", "fish"):
        status_var = r"$status"
        pipestatus_var = r"$pipestatus"

    # If check argument is false, we won't exit after a non-zero exit status.
    # When run in shell that masks pipeline errors (e.g. bash), status_var will be 0 even though an error may have occurred in a pipeline. Ultimately this doesn't matter because we don't care about the exit status of the shell itself.
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
    pipestatus_list = []

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
            raise ShellRunnerError(message)

        capture_output = True
        # If we are still receiving output or poll() is None, we know the command is still running.
        # We must use stdout.read(1) rather than readline() in order to properly print commands that prompt the user for input. We must also forcibly flush the stream in the print statement for the same reason.
        while (out := process.stdout.read(1)) or process.poll() is None:
            # If we detect our marker, we know we are done with the previous command and have printed PIPESTATUS. Capture stdout to pipestatus instead.
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

            # If we detect our marker, we know we have finished capturing PIPESTATUS and can start printing output again.
            if out.startswith("⾏"):
                if pipestatus:
                    pipestatus = pipestatus.split(" : ")[1]
                    # Convert pipestatus to a list of ints: '0 1 0' -> [0, 1, 0]
                    pipestatus_list = [int(x) for x in pipestatus.split()]
                capture_output = True

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
