# AccuSec Architecture Canon

These documents are the **base for AccuSec development**. Designs, APIs, agents, and services must conform to them. Contradictions require an Architecture Decision Record.

| Document | Role |
|---|---|
| [AccuSec_Canon_3_Part_I_Architecture_Vision.md](./AccuSec_Canon_3_Part_I_Architecture_Vision.md) | Part I — architecture vision, principles, invariants, actors, autonomy model, non-goals |
| [Canon_3_Logical_AccuSec_Architecture.md](./Canon_3_Logical_AccuSec_Architecture.md) | Part II — high-level logical architecture; component contracts and trust boundaries |
| [Accusec-detailed-architecture-part1.md](./Accusec-detailed-architecture-part1.md) | Semantic model: Principal + Operation + Entity + Scope + Conditions |
| [Architecture_Diagram.png](./Architecture_Diagram.png) | Canonical high-level architecture diagram |

Word originals (same content) are kept beside the markdown extracts for source-of-truth comparison.

## How to use

1. Read Part I before adding a component or changing a trust boundary.
2. Read Part II before implementing a layer folder.
3. Use the semantic-model document for entity IDs, memory, context packages, RBAC, and audit correlation.
4. Treat the diagram as the authorized map of regions, solid (sync) vs dashed (async) interactions, and external vs platform boundaries.
