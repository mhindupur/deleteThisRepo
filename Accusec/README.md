# AccuSec

AccuSec is an Enterprise AI Operating System for datacenter management. This folder is the base project inside the DatacenterAgent repository.

## Architecture documents

Canonical architecture and vision documents are in [`Documents/`](./Documents/). Prefer the markdown extracts for search and agent context; Word files are the originals.

- `AccuSec_Canon_3_Part_I_Architecture_Vision.md` — Part I architecture vision
- `Canon_3_Logical_AccuSec_Architecture.md` — Part II logical architecture
- `Accusec-detailed-architecture-part1.md` — semantic model (Principal + Operation + Entity + Scope)
- `AccuSec_Enterprise_AI_Operating_System_Architecture.png` — canonical architecture diagram
- `Architecture_Diagram.png` — prior architecture diagram extract

## Project structure

Each logical component from the AccuSec architecture has a dedicated folder with a README stub.

```
Accusec/
├── Documents/                  # Architecture canon
├── shared/                     # Domain models and API contracts
├── interfaces/                 # User interfaces (desktop, web, chat, API, SDK)
├── orchestration/              # AI orchestration (planner, workflow, scheduler)
├── agents/                     # Agent framework, skills, harness, MCP client
│   └── enterprise-ai-engineers/hybrid-cloud/<provider>/
├── integration/
│   ├── connectors/hybrid-cloud/<provider>/
│   └── mcp-servers/<provider>/   # AWS first; Azure, GCP, VMware, Nutanix later
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

## Getting started (local AWS slice)

The first runnable slice is memory-first Hybrid Cloud / AWS. Entity memory is **MySQL** (database `accusec`). Pytest uses fixtures; a live account is optional.

```bash
cd Accusec
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
mysql -uroot < data/operational-db/schema.sql
pytest
accusec serve
# open http://127.0.0.1:8477 — register IAM role, then ask from the console
accusec "list out all t2.small in US-east-1"
accusec --inspect-db
```

To pull **real** AWS inventory, create IAM role `AccuSecInventoryReader` and register it as a secret-ref (never in chat). See [`integration/connectors/hybrid-cloud/aws/iam/README.md`](./integration/connectors/hybrid-cloud/aws/iam/README.md).

```bash
pip install -e ".[aws]"
accusec secrets put aws/operator \
  --auth-mode assume-role \
  --role-arn arn:aws:iam::ACCOUNT:role/AccuSecInventoryReader \
  --external-id accusec-local \
  --profile default
accusec provider connect aws --account ACCOUNT --regions us-east-1 --secret-ref aws/operator
accusec provider sync --region us-east-1
accusec provider status
```

- List uses Entity Memory (SQLite) after query-time authorization; LLM is not used.
- Stop without `instance_id` returns Planner clarification (not HITL).
- Stop with a chosen instance refreshes AWS (fixture connector), then HITL approval, then postcondition check.

1. Read the architecture documents in `Documents/`.
2. Read [`AGENTS.md`](./AGENTS.md) and fill in ownership for your team.

## Status

Local Hybrid Cloud / AWS slice implemented under component `src/` folders. Other layers remain stubs.
