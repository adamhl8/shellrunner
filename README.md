# python-shellrunner

Write safe shell scripts in python.

## Install

No dependencies required.

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
result = X("echo hello world | sed 's/world/there/'").out
greeting = result.capitalize()
X(f"echo 'echo {greeting}' >> .bashrc")
```

An exception is raised if a command exits with a non-zero status (like bash's `set -e`):

```python
X("curl https://invalid.url -o ~/super_important.tar.gz") # curl exits with exit status of 6
# ^ Raises ShellCommandError so the rest of the script doesn't run
X("tar -vxzf ~/super_important.tar.gz")
```

Or, maybe you want to handle the error:

```python
try:
    X("curl https://invalid.url -o ~/super_important.tar.gz")
except ShellCommandError:
    X("curl https://definitely-valid.url -o ~/super_important.tar.gz")
X("tar -vxzf ~/super_important.tar.gz")
```

Pipeline errors are not masked (like bash's `set -o pipefail`):

```python
X("grep hello /non/existent/file | tee new_file")
# ^ Raises ShellCommandError
```

## Why?

> Why not just use bash with `set -e` and `set -o pipefail`?

Because writing anything remotely complicated in bash kinda sucks :)

One of the primary advantages of ShellRunner's approach is that you can seamlessly swap between the shell and Python. Some things are just easier to do in a shell (e.g. pipelines) and a lot of things are easier/better in Python (control flow, error handling, etc).

Also, users of [fish](https://github.com/fish-shell/fish-shell) might know that it [does not offer a way to easily exit a script if a command fails](https://github.com/fish-shell/fish-shell/issues/510). ShellRunner adds `set -e` and `pipefail` like functionality to any shell. Leverage the improved syntax of your preferred shell and the (optional) saftey of bash.

### Similar Projects

zx
zx-py

## Advanced Usage

A note on compatability: ShellRunner should work with on any POSIX-compliant system (and shell). No Windows support at this time.

Confirmed compatible with `sh` (dash), `bash`, `zsh`, and `fish`.

Commands are automatically run with the shell that invoked your python script (this can be overridden):

```python
# my_script.py
X("echo hello | string match hello")
# Works if my_script.py is executed under fish. Will obviously fail if using bash.
```

`X` returns a `NamedTuple` containing the output of the command and a list of its exit status(es), accessed via `.out` and `.status` respectively.

```python
result = X("echo hello")
print(f'Got output "{result.out}" with exit status {result.status}')
# Or unpack
output, status = X("echo hello")
# output = "hello"
# status = [0]
```

`status` will contain the exit status of every command in a pipeline:

```python
statuses = X("echo hello | grep hello").status
# statuses = [0, 0]
```

If using a shell that does not support `PIPESTATUS` such as `sh`, you will only ever get the status of the last command in a pipeline. **This also means that in this case ShellRunner cannot detect if an error occured in a pipeline:**

```python
status = X("grep hello /non/existent/file | tee new_file").status
# if invoked with e.g. bash: ShellCommandError is raised
# if invoked with sh: No exception is raised and status = [0]
```

### Multiple Commands

Sometimes you might want to do something like this:

```python
# Pretend current working directory is ~/
X("curl https://definitely-valid.url -o /tmp/super_important.tar.gz")
X("cd /tmp/")
X("tar -vxzf super_important.tar.gz")
# ^ Raises exception because tar cannot find the file
```

This fails because each call of `X` invokes a new instance of the shell, so things like `cd` don't persist.

A (bad) solution would be to do this:

```python
X("""
curl https://definitely-valid.url -o /tmp/super_important.tar.gz
cd /tmp/
tar -vxzf super_important.tar.gz
""")
```

However, this sort of defeats the purpose of ShellRunner because that would be run as one command, so no error handling can take place.

Instead, `X` also accepts a list of commands:

```python
X([
"curl https://definitely-valid.url -o /tmp/super_important.tar.gz",
"cd /tmp/",
"tar -vxzf super_important.tar.gz"
])
# Works!
```

Each command is run in the same shell instance and goes through the normal error checking.

## Options

There are a few keyword arguments you can provide to adjust the behavior of `X`:

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
