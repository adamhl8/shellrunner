<div align="center">
  <img width="250" src="https://user-images.githubusercontent.com/1844269/226196799-402898d6-c363-4735-be23-57c0ba9e1035.png">
</div>
<br>
<p align="center">
  Write safe shell scripts in Python.
  <br>
  Combine the streamlined utility of a shell with the power of a modern programming language.
</p>

---

- [Install](#install)
- [Usage](#usage)
- [Why?](#why)
  - [Similar Projects](#similar-projects)
- [Advanced Usage](#advanced-usage)
  - [Shell Command Result](#shell-command-result)
  - [Exception Handling](#exception-handling)
  - [Multiple Commands / Persisting Environment](#multiple-commands--persisting-environment)
- [Options](#options)
  - [Output](#output)
  - [Environment Variables](#environment-variables)
- [Examples](#examples)

## Install

```
pip install -U python-shellrunner
```

## Usage

```python
from shellrunner import X

X("echo hello world")
# hello world
```

Easily get a command's output, do something with it, and run another command using the value:

```python
output = X("echo hello world | sed 's/world/there/'").out
greeting = output.capitalize()
X(f"echo 'echo {greeting}' >> .bashrc")
```

An exception is raised if a command exits with a non-zero status (like bash's `set -e`):

```python
text = X("grep hello /non/existent/file").out # grep exits with a non-zero status
# ^ Raises ShellCommandError so the rest of the script doesn't run
my_text_processor(text)
```

Or, maybe you want to handle the error:

```python
from shellrunner import X, ShellCommandError

text = ""
try:
    text = X("grep hello /non/existent/file").out
except ShellCommandError:
    text = X("grep hello /file/that/definitely/exists").out
my_text_processor(text)
```

Pipeline errors are not masked (like bash's `set -o pipefail`):

```python
X("grep hello /non/existent/file | tee new_file") # tee gets nothing from grep, creates an empty file, and exits with status 0
# ^ Raises ShellCommandError
```

## Why?

> Why not just use bash with `set -e` and `set -o pipefail`?

Because writing anything remotely complicated in bash kinda sucks :)

One of the primary advantages of ShellRunner's approach is that you can seamlessly swap between the shell and Python. Some things are just easier to do in a shell (e.g. pipelines) and a lot of things are easier/better in Python (control flow, error handling, etc).

Also, users of [fish](https://github.com/fish-shell/fish-shell) might know that it [does not offer a way to easily exit a script if a command fails](https://github.com/fish-shell/fish-shell/issues/510). ShellRunner adds `set -e` and `pipefail` like functionality to any shell. Leverage the improved syntax of your preferred shell and the (optional) saftey of bash.

### Similar Projects

- [zxpy](https://github.com/tusharsadhwani/zxpy)
- [shellpy](https://github.com/lamerman/shellpy)
- [plumbum](https://github.com/tomerfiliba/plumbum)

ShellRunner is very similar to zxpy and shellpy but aims to be more simple in its implementation and has a focus on adding safety to scripts.

## Advanced Usage

A note on compatability: ShellRunner should work with on any POSIX-compliant system (and shell). No Windows support at this time.

Confirmed compatible with `sh` (dash), `bash`, `zsh`, and `fish`.

Commands are automatically run with the shell that invoked your python script (this can be [overridden](#options)):

```python
# my_script.py
X("echo hello | string match hello")
# Works if my_script.py is executed under fish. Will obviously fail if using bash.
```

### Shell Command Result

`X` returns a `ShellCommandResult` (`NamedTuple`) containing the following:

- `out: str`: The `stdout` and `stderr` of the command.
- `status: int`: The overall exit status of the command. If the command was a pipeline that failed, `status` will be equal to the status of the last failing command (like bash's `pipefail`).
- `pipestatus: list[int]`: A list of statuses for each command in the pipeline.

```python
result = X("echo hello")
print(f'Got output "{result.out}" with exit status {result.status} / {result.pipestatus}')
# Or unpack
output, status, pipestatus = X("echo hello")
# output = "hello"
# status = 0
# pipestatus = [0]
```

```python
result = X("(exit 1) | (exit 2) | echo hello")
# result.out = "hello"
# result.status = 2
# result.pipestatus = [1, 2, 0]
```

If using a shell that does not support `PIPESTATUS` such as `sh`, you will only ever get the status of the last command in a pipeline. **This also means that in this case ShellRunner cannot detect if an error occured in a pipeline:**

```python
result = X("(exit 1) | echo hello")
# if invoked with bash: ShellCommandError is raised, status = 1, pipestatus = [1, 0]
# if invoked with sh: No exception is raised, status = 0, pipestatus = [0]
```

### Exception Handling

`ShellCommandError` also receives the information from the failed command, which means you can do something like this:

```python
try:
    X("echo hello && false") # Pretend this is some command that prints something but exits with a non-zero status
except ShellCommandError as e:
    print(f'Command failed. Got output "{e.out}" with exit status {e.status}')
```

### Multiple Commands / Persisting Environment

Each call of `X` invokes a new instance of the shell, so things like environment variables or directory changes don't persist.

Sometimes you might want to do something like this:

```python
X("MY_VAR=hello")
X("grep $MY_VAR /file/that/exists") # MY_VAR doesn't exist
# ^ Raises ShellCommandError
```

A (bad) solution would be to do this:

```python
X("MY_VAR=hello; grep $MY_VAR /file/that/exists")
```

This sort of defeats the purpose of ShellRunner because that would be run as one command, so no error handling can take place on commands before the last one.

Instead, `X` also accepts a list of commands where each command is run in the same shell instance and goes through the normal error handling:

```python
X([
"MY_VAR=hello",
"grep $MY_VAR /file/that/exists",
])
# Works!
```

## Options

There are a few keyword arguments you can provide to adjust the behavior of `X`:

```python
X("command", shell="bash", check=True, show_output=True, show_commands=True)
```

`shell: str` (Default: the invoking shell) - Shell that will be used to execute the commands. Can be a path or simply the name (e.g. "/bin/bash", "bash").

`check: bool` (Default: True) - If True, an error will be thrown if a command exits with a non-zero status.

`show_output: bool` (Default: True) - If True, command output will be printed.

`show_commands: bool` (Default: True) - If True, the current command will be printed before execution.

### Output

Say you do this:

```python
X("echo hello world")
```

This will print the following to your terminal:

```
Executing: echo hello world
hello world
```

To hide the `Executing:` lines, set `show_commands=False`.

To hide actual command output, set `show_output=False`.

### Environment Variables

Each option also has a corresponding environment variable to allow you to set these options "globally" for your script:

`shell` = `SHELLRUNNER_SHELL`

`check` = `SHELLRUNNER_CHECK`

`show_output` = `SHELLRUNNER_SHOW_OUTPUT`

`show_commands` = `SHELLRUNNER_SHOW_COMMANDS`

Environment variables are evaluated on each call of `X`, so you could also do something like this:

```python
# Pretend that before running this file you set: export SHELLRUNNER_SHOW_OUTPUT="False"
X("echo hello")
# No output

# Now you want to see output
os.environ["SHELLRUNNER_SHOW_OUTPUT"] = "True"
X("echo hello")
# hello
```

## Examples

Prints out installed python packages and their dependencies:

```python
from shellrunner import X

packages = X("pip list -l | sed 1,2d | awk '{print $1}'").out
packages = packages.splitlines()

for package in packages:
    print(f"=== {package} ===")
    X(f"pip show {package} | grep -E 'Requires|Required-by'", show_commands=False)
```
