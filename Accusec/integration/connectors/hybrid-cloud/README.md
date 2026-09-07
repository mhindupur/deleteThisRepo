# Hybrid Cloud Connectors

**Layer:** Integration

Connectors for each infrastructure platform. Vendor SDKs live here only.

## Status

Scaffold — `aws/` connector folder exists; implementation pending.

## Provider connectors

| Provider | Path |
|---|---|
| AWS | [`aws/`](./aws/) |

Add sibling folders for Azure, GCP, VMware, Nutanix, Kubernetes, and others.
Do not call vendor APIs from agents or skills.

## Planned contents

- `src/` — shared connector interface (auth, normalize, retry)
- `tests/` — interface tests
- `<provider>/` — vendor implementation
