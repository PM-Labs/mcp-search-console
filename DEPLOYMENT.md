# Deployment

This MCP server is deployed to the Pathfinder DO droplet as a Docker container.

## Quick Reference

| Field | Value |
|---|---|
| Droplet | `mcp-server` |
| Service name | `search-console` |
| URL | `https://search-console.mcp.pathfindermarketing.com.au/mcp` |
| Docker image | `australia-southeast1-docker.pkg.dev/pathfinder-383411/cloud-run-source-deploy/search-console-mcp:latest` |
| Env file | `/opt/pmin-mcpinfrastructure/env/search-console.env` |
| Full docs | [PM-Labs/pmin-mcpinfrastructure](https://github.com/PM-Labs/pmin-mcpinfrastructure) -> `docs/runbooks/search-console.md` |

## Deploy

```bash
gcloud builds submit --tag australia-southeast1-docker.pkg.dev/pathfinder-383411/cloud-run-source-deploy/search-console-mcp --project pathfinder-383411
ssh mcp-server "cd /opt/pmin-mcpinfrastructure && docker compose pull search-console && docker compose up -d search-console"
```

## Rollback

```bash
ssh mcp-server "cd /opt/pmin-mcpinfrastructure && docker compose stop search-console"
# Revert to previous image tag, then: docker compose up -d search-console
```

## Operational Docs

See [PM-Labs/pmin-mcpinfrastructure](https://github.com/PM-Labs/pmin-mcpinfrastructure) for:
- Architecture: `docs/ARCHITECTURE.md`
- Runbook: `docs/runbooks/search-console.md`
- Cron jobs: `docs/CRON-JOBS.md`
