# Hybrid Cloud Engineer

**Layer:** Agent Framework

Domain agent for hybrid cloud operations. Provider-specific code is a **pack**
under this folder (AWS first), not a separate Enterprise AI Engineer.

See [PROVIDERS.md](./PROVIDERS.md) for the pack contract used by AWS, Azure,
GCP, VMware, Nutanix, and future platforms.

## Status

Scaffold — AWS pack folder exists; implementation pending.

## Provider packs

| Provider | Path |
|---|---|
| AWS | [`aws/`](./aws/) |
| Azure, GCP, VMware, Nutanix, … | Add sibling folders with the same layout |

## Planned contents

- `src/` — Hybrid Cloud Engineer runtime definition shared across providers
- `tests/` — engineer selection and entitlement tests
- `<provider>/` — allowed skills, tools, and default scopes
