# Web Console

**Layer:** User Interfaces

Desktop-profile operator console. Chat is a client of the HTTP API; the orchestrator remains the system of record.

## Status

Runnable for the Hybrid Cloud / AWS slice. Full Enterprise React/TypeScript console is still a later packaging of the same contracts.

## Run

```bash
cd Accusec
pip install -e ".[dev,aws]"
accusec serve
```

Open `http://127.0.0.1:8477`.

## This slice

- Register an IAM role as an Endpoint Access Identity (secret-ref). Credentials never enter chat.
- List reads Organizational Memory first (MySQL `entities`).
- Stop: AccuSec execution policy → memory lookup → AWS refresh via MCP/connector → HITL confirm → stop → postcondition upsert.

## Architecture references

- `Documents/AccuSec_Canon_3_Part_I_Architecture_Vision.md`
- `Documents/Canon_3_Logical_AccuSec_Architecture.md`
- `Documents/AccuSec Tenancy, Projects, Datacenters, IAM and Organizational Memory Access — Consolidated PRD.md`
