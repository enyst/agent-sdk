# openhands-workspace

Workspace implementations for OpenHands.

## Optional Daytona dependency

The `DaytonaWorkspace` requires the Daytona Python SDK, which is **not installed by default**.

Install the optional extra:

```bash
uv pip install 'openhands-workspace[daytona]'
```

Then you can import it (lazy-imported from the top-level module):

```python
from openhands.workspace import DaytonaWorkspace
```
