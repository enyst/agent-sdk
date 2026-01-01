# openhands-workspace

Workspace implementations for OpenHands.

## Optional Daytona dependency

The `DaytonaWorkspace` requires the Daytona Python SDK, which is **not installed by default**.

Install it with:

```bash
uv pip install daytona
```

Or with pip:

```bash
pip install daytona
```

Then you can use `DaytonaWorkspace` from:

```python
from openhands.workspace import DaytonaWorkspace
```
