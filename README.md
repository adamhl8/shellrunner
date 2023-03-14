# python-shellrunner

### Example

```python
from shellrunner import X

packages = X("pip list -l | sed 1,2d | awk '{print $1}'").output
packages = packages.splitlines()

for package in packages:
    print(f"=== {package} ===")
    X(f"pip show {package} | grep -E 'Requires|Required-by'", print_commands=False)
```
