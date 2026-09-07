# MCP Servers

**Layer:** Integration

MCP server implementations. One server process (or package) **per provider**
so AWS, Azure, GCP, VMware, and Nutanix tools stay isolated.

The MCP client and registry remain shared. A newly advertised tool is not
executable until it is registered, allowlisted, and policy-approved.

## Status

Scaffold — `aws/` server folder exists; implementation pending.

## Provider servers

| Provider | Path |
|---|---|
| AWS | [`aws/`](./aws/) |

Add sibling folders `azure/`, `gcp/`, `vmware/`, `nutanix/` with the same
`src/` + `tests/` layout.

## Planned contents

- `src/` — shared MCP server host helpers (optional)
- `tests/` — registry contract tests
- `<provider>/` — vendor tool schemas and handlers
