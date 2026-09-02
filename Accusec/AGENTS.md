# AccuSec — Agent & Collaborator Guide

Instructions for humans and Cursor agents working in `Accusec/`.

## What AccuSec is

AccuSec is an Enterprise AI Operating System for datacenter management. This tree is a multi-component scaffold inside the DatacenterAgent repository. Architecture canon lives in [`Documents/`](./Documents/).

## Before you start

1. Sync `main` before creating a branch.
2. Work only in the folders you own (see [Component ownership](#component-ownership)).
3. Treat `shared/` as a coordination zone — do not change schemas there without agreeing with other owners.
4. Prefer one short-lived PR per component (or a small slice of one component).

## Branch and PR conventions

| Rule | Detail |
|------|--------|
| Branch from | `main` |
| Branch name | `cursor/<component>-<short-description>` (e.g. `cursor/platform-context-service`) |
| Scope | One logical component or a clear vertical slice |
| PR target | `main` |
| PR style | Draft early; mark ready when tests/docs are in place |
| Merge | Squash or merge after review; then delete the branch |

### Suggested workflow

```bash
git checkout main
git pull origin main
git checkout -b cursor/<component>-<short-description>
# implement inside Accusec/<your-folders>/
git push -u origin HEAD
# open PR → review → merge
```

After merge:

```bash
git checkout main
git pull origin main
```

## Component ownership

Fill in names so collaborators and agents know who owns what. Update this table when ownership changes.

| Area | Path | Owner | Notes |
|------|------|-------|-------|
| Shared contracts | `shared/` | _TBD (coordinate)_ | Schema/API changes need agreement before merge |
| User interfaces | `interfaces/` | _TBD_ | |
| AI orchestration | `orchestration/` | _TBD_ | |
| Agent framework | `agents/` | _TBD_ | |
| Platform services | `platform-services/` | _TBD_ | |
| Organizational memory | `memory/` | _TBD_ | |
| Data layer | `data/` | _TBD_ | |
| Integration | `integration/` | _TBD_ | |
| AI gateway | `ai/` | _TBD_ | |
| Security & governance | `security/` | _TBD_ | |
| Platform foundation | `foundation/` | _TBD_ | |
| Architecture docs | `Documents/` | _TBD_ | Prefer PRs for doc updates |

### Example split (edit to match your team)

| Person | Owns |
|--------|------|
| Person A | `platform-services/`, `memory/`, `security/` |
| Person B | `agents/`, `orchestration/`, `ai/` |
| Both (coordinate) | `shared/`, integration seams between owned areas |

## Integration rules

1. **Contracts first.** If two components must talk, add or update types/schemas under `shared/` in a dedicated PR, then implement against that contract.
2. **Do not edit another owner's folders** in the same PR unless they asked for a small fix and are on the review.
3. **Keep PRs small.** Prefer merging often over long-lived branches.
4. **Rebase or merge `main` regularly** into your feature branch to reduce conflicts.
5. **Unifying model** (from architecture docs) — keep designs aligned with:

   ```
   Principal + Operation + Entity + Scope + Conditions
       → Authorization → Context Assembly → Context Package
       → Plan → Skill Harness → Audit
   ```

## Cursor collaboration

### Desktop

- Open this repository in Cursor Desktop.
- Use Local Agent mode for work on your branch.
- Stay inside owned folders under `Accusec/`.

### Cloud Agents

- Start Cloud Agents against this GitHub repo (not a different identity).
- Point the agent at a specific component path and task.
- Cloud Agents should open a PR on a feature branch for review.

### PR follow-ups

- Comment `@cursor` on a PR to request fixes, conflict resolution, or review follow-ups.
- Share agent run URLs or PR links when handing work to a teammate.

## What agents should do

- Read this file and the component `README.md` before changing code.
- Prefer implementing under the matching folder (`src/`, `tests/` as described in that README).
- Do not invent a parallel folder layout outside the scaffold.
- Do not rewrite architecture docs unless asked.
- When touching `shared/`, call out contract impact in the PR description.
- Leave services running after local testing; do not kill unrelated processes.

## What agents should not do

- Modify unrelated components “while here.”
- Broad dependency upgrades or lockfile rewrites unless requested.
- Commit secrets, tokens, or private keys.
- Force-push or amend shared history unless explicitly asked.

## Architecture references

These documents are the development baseline. Do not contradict them without an ADR.

- `Documents/README.md` — canon index
- `Documents/AccuSec_Canon_3_Part_I_Architecture_Vision.md`
- `Documents/Canon_3_Logical_AccuSec_Architecture.md`
- `Documents/Accusec-detailed-architecture-part1.md`
- `Documents/Architecture_Diagram.png`
- Root overview: [`README.md`](./README.md)

## Status

Scaffold only. Most folders contain README stubs. Implementation is pending.
