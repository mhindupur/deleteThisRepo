# AccuSec

AccuSec is an Enterprise AI Operating System for datacenter management. This folder is the base project inside the DatacenterAgent repository.

## Architecture documents

Canonical architecture and vision documents are in [`Documents/`](./Documents/). Prefer the markdown extracts for search and agent context; Word files are the originals.

- `AccuSec_Canon_3_Part_I_Architecture_Vision.md` — Part I architecture vision
- `Canon_3_Logical_AccuSec_Architecture.md` — Part II logical architecture
- `Accusec-detailed-architecture-part1.md` — semantic model (Principal + Operation + Entity + Scope)
- `Architecture_Diagram.png` — canonical architecture diagram

## Project structure

Each logical component from the AccuSec architecture has a dedicated folder with a README stub.

```
Accusec/
├── Documents/                  # Architecture canon
├── shared/                     # Domain models and API contracts
├── interfaces/                 # User interfaces (desktop, web, chat, API, SDK)
├── orchestration/              # AI orchestration (planner, workflow, scheduler)
├── agents/                     # Agent framework, skills, harness, MCP client
├── platform-services/          # Context, auth, policy, audit, notifications, etc.
├── memory/                     # Organizational memory stores
├── data/                       # Data layer adapters (PostgreSQL, vector, graph, etc.)
├── integration/                # Connectors, collectors, gateway, event bus
├── ai/                         # AI gateway and model providers
├── security/                   # RBAC, tenancy, privacy, compliance
└── foundation/                 # Kubernetes, CI/CD, IaC, monitoring, logging
```

## Core semantic model

AccuSec unifies memory, context, and authorization around:

```
Principal + Operation + Entity + Scope + Conditions
    → Authorization → Context Assembly → Context Package → Plan → Skill Harness → Audit
```

## Collaboration

See [`AGENTS.md`](./AGENTS.md) for branch/PR conventions, component ownership, and Cursor collaboration guidance.

## Getting started

1. Read the architecture documents in `Documents/`.
2. Read [`AGENTS.md`](./AGENTS.md) and fill in ownership for your team.
3. Browse component README stubs for the area you are implementing.
4. Implement services under the matching folder following the planned `src/` and `tests/` layout in each README.

## Status

Repository scaffold — folder structure and README stubs only. Implementation pending.
