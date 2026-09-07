# System Skills

**Layer:** Agent Framework

Versioned, reusable skill definitions for governed tool execution.

Skills are grouped by **provider** so AWS, Azure, GCP, VMware, Nutanix, and
on-prem packs can land without sharing modules.

## Status

Scaffold — `aws/` pack folder exists; implementation pending.

## Provider skills

| Provider | Path |
|---|---|
| AWS | [`aws/`](./aws/) |

Add `azure/`, `gcp/`, `vmware/`, `nutanix/` as sibling folders using the AWS
README as the template.

## Planned contents

- `src/` — shared skill schema / loader
- `tests/` — schema tests
- `<provider>/` — provider skill manifests
