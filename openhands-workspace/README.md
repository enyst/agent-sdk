# openhands-workspace

Workspace implementations for OpenHands.

## Available workspaces

- `DockerWorkspace`: run agent-server in a local Docker container.
- `DockerDevWorkspace`: like DockerWorkspace, but builds the image locally.
- `ApptainerWorkspace`: run agent-server with Apptainer.
- `APIRemoteWorkspace`: connect to an agent-server managed by the OpenHands Runtime API.
- `OpenHandsCloudWorkspace`: provision an OpenHands Cloud sandbox and connect to its agent-server.

## Daytona (optional)

`DaytonaWorkspace` provisions a Daytona Cloud sandbox and exposes the agent-server via Daytona preview links.

Install the optional dependency:

```bash
uv pip install 'openhands-workspace[daytona]'
```

Then import it (lazy-imported):

```python
from openhands.workspace import DaytonaWorkspace
```
