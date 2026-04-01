# selu-agent-pdf

Selu agent that creates PDF documents from structured content and optional
images, then returns an artifact reference that can be passed to email tools.

## Local build

```bash
./build.sh
```

This will:

1. Build the capability image `selu-cap-pdf:latest`
2. Create `agent.tar.gz` for marketplace/manual installation
