# Hybrid Cloud Engineer — AWS pack

**Layer:** Agent Framework  
**Provider:** AWS  
**Parent:** `agents/enterprise-ai-engineers/hybrid-cloud/`

AWS-specific mission, skill allowlist, tool allowlist, and default scope for
the Hybrid Cloud Engineer. This is not a standalone AccuSec agent that bypasses
orchestration, policy, or the skill harness.

## Status

Local fixture-backed implementation in `src/` (no live AWS account). List is memory-first; stop uses Planner clarification then HITL.

## Owns

- AWS engineer definition (instructions, evaluation rules, risk limits)
- Which AWS skills this pack may invoke
- Default AWS scope: tenant, workspace, account_id, regions
- Mapping of user intent onto AWS operations in the catalog

## Does not own

- boto3 / AWS API calls → `integration/connectors/hybrid-cloud/aws/`
- MCP tool implementations → `integration/mcp-servers/aws/`
- Skill procedures → `agents/skills/aws/`
- Authorization, secrets, audit → platform services

## First slice (A0)

Intent: explain health or latency for an in-scope AWS resource (EC2 instance or
EKS cluster) using authorized context only. No StartInstances / StopInstances /
mutating APIs.

## Planned contents

- `src/` — pack definition (YAML or code): allowed skills, tools, scopes
- `tests/` — pack entitlement tests (cannot call undeclared tools)
