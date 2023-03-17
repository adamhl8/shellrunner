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

# Easily get stdout
result = X("echo hello world | sed 's/world/there/'").out
# hello there
greeting = result.capitalize()
```

```python
X("curl ")
```

### Example

```python
from shellrunner import X

packages = X("pip list -l | sed 1,2d | awk '{print $1}'").out
packages = packages.splitlines()

for package in packages:
    print(f"=== {package} ===")
    X(f"pip show {package} | grep -E 'Requires|Required-by'", show_commands=False)
```
