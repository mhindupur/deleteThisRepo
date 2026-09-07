# AWS MCP Server

**Layer:** Integration  
**Provider:** AWS

MCP server that exposes **registered AWS tools** to the AccuSec MCP client.
Dynamic discovery is not trust: tools execute only when listed in the MCP
Server Registry, entitled to the Hybrid Cloud AWS pack, and allowed by policy.

## Status

Scaffold — implementation pending.

## Boundary

```
Skill Harness → MCP Client → this server → AWS connector → AWS API
```

This server MUST:

- Validate tool name and JSON Schema inputs
- Bind tenant, workspace, principal, scope, correlation ids
- Call `integration/connectors/hybrid-cloud/aws/` (not boto3 in tool handlers long-term)
- Return normalized AccuSec entities plus provenance (`source`, `observed_at`)
- Never log or return secret values
- Classify each tool: read vs write, risk, idempotent, approval_default

## A0 tool catalog

| Tool | Operation catalog | Side effect |
|---|---|---|
| `aws.sts.get_caller_identity` | `resource.read` | none |
| `aws.ec2.describe_instances` | `compute.instance.list` / `read` | none |
| `aws.ec2.describe_instance_status` | `compute.instance.read` | none |
| `aws.cloudwatch.get_metric_statistics` | `resource.read` | none |
| `aws.ec2.describe_vpcs` | `network.read` | none |

Write tools (`start_instances`, `stop_instances`, `reboot_instances`,
`create_*`) stay unimplemented until A2 + HITL.

## Sibling servers

Add `integration/mcp-servers/azure`, `gcp`, `vmware`, `nutanix`, and others
with the same contract. Do not merge vendor tool handlers into one server.

## Planned contents

- `src/` — MCP server process, tool schemas, handlers
- `tests/` — schema tests, allowlist tests, recorded AWS responses
