from dataclasses import dataclass
from pathlib import Path


@dataclass
class Options:
    shell: str = ""
    shell_path: Path = Path()
    check: bool = True
    pipefail: bool = True
    show_output: bool = True
    show_commands: bool = True


def X(  # noqa: N802
    *,
    shell: str | None = None,
    check: bool | None = None,
    pipefail: bool | None = None,
    show_output: bool | None = None,
    show_commands: bool | None = None,
):
    x_options = {
        "shell": shell,
        "check": check,
        "pipefail": pipefail,
        "show_output": show_output,
        "show_commands": show_commands,
        "invalid_key": False,
    }

    specified_options = {k: v for k, v in x_options.items() if v is not None}
    print(specified_options)
    resolved_options = Options(**specified_options)
    print(resolved_options)


X(shell="noice", check=False)
