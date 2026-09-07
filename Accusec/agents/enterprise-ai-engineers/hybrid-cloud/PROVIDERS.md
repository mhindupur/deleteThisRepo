# Hybrid Cloud provider packs

Vendor-specific agent code lives **under** the Hybrid Cloud Engineer, not as a
peer Enterprise AI Engineer. Canon 3 treats Hybrid Cloud as the domain agent.
AWS, Azure, GCP, VMware, Nutanix, and other platforms are **provider packs**.

## Layout

```
agents/enterprise-ai-engineers/hybrid-cloud/
  PROVIDERS.md          # this file
  README.md             # Hybrid Cloud Engineer
  aws/                  # this team's pack
  azure/                # sibling pack (add when owned)
  gcp/
  vmware/
  nutanix/
  <provider>/

agents/skills/<provider>/
integration/connectors/hybrid-cloud/<provider>/
integration/mcp-servers/<provider>/
```

The MCP client (`agents/mcp-client/`) stays shared. It must not import AWS or
any other vendor SDK.

## Pack contract

Each provider pack MUST supply:

| Piece | Path | Responsibility |
|---|---|---|
| Connector | `integration/connectors/hybrid-cloud/<provider>/` | Auth, pagination, retries, normalize vendor API → AccuSec entities |
| MCP server | `integration/mcp-servers/<provider>/` | Registered, schema-validated tools. No tools execute without registry + allowlist |
| Skills | `agents/skills/<provider>/` | How to accomplish a domain task (diagnose, list, plan). Skills call tools via the harness |
| Engineer pack | `agents/enterprise-ai-engineers/hybrid-cloud/<provider>/` | Allowed skills, tool allowlist, default scope (account/subscription/cluster), risk limits |

## Rules

- Agents MUST NOT call vendor SDKs (`boto3`, Azure SDK, govc, Prism) directly.
- Secrets stay in Security and Secrets Manager. Tools receive short-lived scoped credentials.
- Discovery of an MCP tool does not grant execution. Registry + policy + harness decide.
- Start at autonomy **A0 (Observe)**. Writes require A2 and plan-versioned approval.
- Entity IDs use AccuSec canonical ids, not display names.
- Sibling providers copy this contract; they do not fork the Hybrid Cloud Engineer.
