CANON 3
AccuSec Architecture
Part I — Architecture Vision
Enterprise AI Operating System

Document status: Draft 0.1 29 July 2026 Owner: AccuSec Architecture

Document Purpose
This chapter defines the architecture vision for the AccuSec Enterprise AI Operating System. It establishes the architectural problem, scope, principles, invariants, boundaries, operating model, and decision criteria that govern all later Canon 3 chapters. It is not a product brochure and it is not a low-level design. Its purpose is to constrain design choices so that independently designed components converge into one coherent, secure, observable, extensible system.
Normative status Statements using MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are architectural requirements. Later component designs may refine these requirements but may not contradict them without an explicit Architecture Decision Record and approval by the architecture review authority.

Document Scope
Defines what AccuSec is architecturally and what it is not.
Establishes the first product boundary: Hybrid Cloud Infrastructure Management.
Defines the system’s primary actors, trust model, execution model, and deployment continuum.
Introduces the core logical concepts used in Part II: interfaces, orchestration, agents, skills, harness, MCP, platform services, data services, connectivity, model access, security, and foundation services.
Sets measurable quality attributes and architectural acceptance criteria.
Creates the vocabulary used across engineering, product, security, operations, and design-partner discussions.
Out of Scope for Part I
Component-level APIs, schemas, database tables, event contracts, and deployment manifests.
Detailed agent graph design, prompt design, model selection algorithms, and evaluation datasets.
Concrete vendor commitments where the architecture remains implementation-neutral.
Use-case-specific workflows such as cluster deployment, remediation, upgrades, or disaster recovery.
Commercial packaging, pricing, licensing, and go-to-market design.

1. Architectural Thesis
AccuSec exists because enterprise production operations require a stronger execution model than general-purpose conversational AI or unconstrained autonomous agents provide. Large language models can reason, generate plans, call tools, and adapt to incomplete information. However, production enterprise systems require every consequential action to be identity-bound, context-aware, policy-constrained, authorized, observable, recoverable, and auditable.
The AccuSec architecture therefore treats the model as a probabilistic reasoning component inside a deterministic enterprise control system. The model may propose, interpret, decompose, rank, and explain. It does not independently become the authority for identity, policy, permission, transaction commitment, or audit truth.
Core architectural thesis Reasoning may be probabilistic. Enterprise execution must be governed and evidence-producing. AccuSec separates the two and binds them through explicit contracts.

1.1 The System We Are Building
AccuSec is an Enterprise AI Operating System: a shared runtime and control plane for Enterprise AI Engineers that reason over enterprise context and perform authorized operations across enterprise systems. Its first domain is Hybrid Cloud Infrastructure Management.
The term “Operating System” is architectural, not metaphorical. AccuSec provides common services that domain AI engineers should not reimplement: identity propagation, policy evaluation, capability discovery, context acquisition, memory, workflow state, scheduling, approvals, secure tool execution, isolation, observability, audit, model access, cost control, and failure recovery.
1.2 The First Domain
The first domain is Hybrid Cloud Infrastructure Management across private cloud, virtualization, Kubernetes, public cloud, edge environments, and related IT operations systems. This domain is deliberately difficult: infrastructure state is distributed, APIs vary, dependencies are deep, operations are privileged, changes can be destructive, and the cost of an incorrect action can be high.
The architecture MUST solve the general enterprise trust problem while remaining concrete enough to deliver five compelling cloud-administrator workflows with the design partner. Architecture is validated through working operational use cases, not through conceptual completeness alone.
2. Architecture Outcomes
The architecture is successful only if it produces outcomes visible to administrators, operators, security teams, developers, and auditors. The following outcomes guide prioritization.
Outcome
Meaning
Evidence
Accurate operations
Plans and actions are grounded in current system state, validated before execution, and verified afterward.
Preconditions, validation results, execution results, postconditions, and reconciliation records.
Secure execution
Every request and action is bound to a verified identity, least-privilege authorization, approved credential path, and explicit target scope.
Authentication claims, policy decision, secret reference, target authorization, audit trail.
Efficient operation
The platform minimizes unnecessary model calls, repeated context retrieval, tool calls, and human interruption.
Latency, token usage, cache hit rate, tool-call count, approval frequency, cost per completed task.
Human control
People retain control over policy, privileges, exceptions, and high-impact decisions.
Approval records, escalation path, policy ownership, break-glass records.
Explainable behavior
The system can explain what it understood, why it chose a plan, what evidence it used, and what happened.
Decision summary, cited context, plan history, tool results, final outcome.
Recoverable workflows
Long-running operations survive process failure and can retry, compensate, resume, or stop safely.
Durable workflow state, checkpoints, idempotency keys, retry history, compensation status.
Extensible platform
New domains, agents, skills, tools, models, and connectors can be added without modifying the trusted core.
Versioned contracts, registration model, compatibility tests, isolation boundaries.
3. Governing Architecture Principles
P1. Separate reasoning from authority
Models and agents MAY propose actions. Identity systems, policy services, approval services, and target systems remain authoritative. No model output alone authorizes an operation.
P2. Context before action
Every operational plan MUST be grounded in a declared context snapshot sufficient for the requested scope. The platform MUST record which context influenced a decision.
P3. Policy at every consequential boundary
Authorization is not a one-time login check. Policy MUST be evaluated at request admission, plan approval, tool invocation, credential use, and high-impact state transition boundaries.
P4. Least privilege and delegated identity
Agents MUST NOT operate as universal superusers. Every operation must execute under an identity or delegated service identity with a bounded capability set, target scope, and lifetime.
P5. Deterministic execution envelope
Probabilistic reasoning MUST be enclosed by deterministic schemas, validation, workflow state, idempotency, timeout, retry, and audit behavior.
P6. Human control is a first-class primitive
Human approval, rejection, modification, escalation, and cancellation are native workflow states, not UI add-ons.
P7. Durable state over hidden conversational state
Business-critical workflow state MUST be persisted outside the model context window. Chat history is not the system of record.
P8. Tool access through governed contracts
Enterprise operations MUST occur through registered, typed, policy-aware tools or APIs. Direct, ungoverned model-to-system access is prohibited.
P9. Evidence-producing operations
Every material action MUST produce sufficient evidence to reconstruct who requested it, what the system knew, what policy allowed it, what was executed, and what changed.
P10. Failure is expected
Components, models, networks, connectors, and target systems will fail. Workflows MUST degrade safely, preserve state, and avoid duplicate or partially hidden actions.
P11. Locality and deployment flexibility
The same logical architecture SHOULD support a laptop/basic deployment and an enterprise private deployment. Components may collapse or scale independently without changing their logical contracts.
P12. Vendor neutrality at logical boundaries
Logical contracts SHOULD not depend on a single model provider, database vendor, message broker, cloud, or infrastructure platform.
P13. Security control planes remain non-generative
Core identity, authorization, policy enforcement, secrets handling, audit integrity, and tenant isolation MUST NOT depend on LLM reasoning for enforcement correctness.
P14. Measure before optimizing autonomy
The platform SHOULD increase autonomy only when evidence shows acceptable accuracy, security, recoverability, and operator trust for a specific workflow.
P15. Product learning constrains platform breadth
The architecture may anticipate multiple domains, but implementation priority MUST be driven by validated Hybrid Cloud use cases and observed administrator behavior.
4. Conceptual Operating Model
An AccuSec operation progresses through a governed lifecycle. This lifecycle is conceptual and remains valid whether the interaction begins from desktop, web, chat, API, schedule, alert, or external system event.
Intent admission — A user or system submits a request. Identity, tenant, session, source, and request metadata are established.
Intent interpretation — The runtime classifies the domain, desired outcome, constraints, risk, and required context.
Context acquisition — Current topology, inventory, configuration, policy, historical operations, tickets, alerts, and other permitted evidence are retrieved.
Planning — One or more candidate plans are created as typed steps with preconditions, expected effects, required tools, risk classification, and approval requirements.
Validation and policy evaluation — The plan is checked against schemas, system capabilities, target state, business rules, RBAC/ABAC, separation of duties, and safety guardrails.
Human decision where required — A person approves, rejects, edits, delegates, or escalates the plan or specific steps.
Credential-bound execution — The skill harness invokes registered tools using scoped credentials, deterministic input contracts, idempotency controls, and timeouts.
Observation and verification — Tool results and external events are collected. Expected postconditions are tested against actual state.
Recovery or continuation — The workflow retries, compensates, pauses, replans, escalates, or continues according to durable state and policy.
Completion and learning — The outcome, evidence, cost, performance, user feedback, and reusable operational memory are recorded.
Architectural consequence The primary unit of work is not a chat message or an LLM call. It is a durable, identity-bound, policy-governed operational task with a complete lifecycle.

5. Primary Actors and Authorities
Actor
Architectural responsibility
Cloud Administrator
Requests operations, reviews plans, grants approvals within assigned authority, and consumes results.
Platform Administrator
Configures tenants, connectors, model policies, operational limits, platform health, and deployment settings.
Security and Compliance Administrator
Owns identity integration, role and attribute policy, approval controls, secret policy, data handling, and audit access.
Enterprise AI Engineer
A domain-bounded agentic capability that interprets intent, plans work, invokes approved skills, and communicates outcomes.
System Skill
A reusable, versioned capability with declared inputs, outputs, side effects, risk, permissions, and operational behavior.
Skill Harness
The controlled runtime that validates, authorizes, executes, observes, retries, and records skill invocations.
MCP Server or API Provider
Exposes discoverable tools and resources over a governed interface. It is not trusted merely because it is discoverable.
Target Enterprise System
The authoritative system being observed or changed, such as vCenter, Nutanix Prism, AWS, Azure, Kubernetes, ServiceNow, or an identity provider.
Identity Provider
Authenticates human and service identities and supplies verifiable claims.
Policy Decision and Enforcement Services
Determine whether an action is allowed and enforce the decision at the relevant boundary.
Model Provider
Provides reasoning or embedding capability through the AI gateway. It is not an enterprise authority.
Auditor or Reviewer
Inspects immutable evidence without receiving operational permissions by implication.
6. Architectural Boundaries
The platform is organized around explicit boundaries because enterprise trust depends on knowing where identity, policy, data, execution, and authority change hands.
Experience boundary: Separates user-facing interfaces and external integrations from platform-internal services. Interfaces may vary; admission controls and core semantics remain consistent.
Tenant boundary: Separates organizations, workspaces, identities, policies, credentials, memory, operational data, quotas, and audit records.
Reasoning boundary: Separates model-generated interpretation and planning from trusted platform state and enforcement services.
Execution boundary: Separates proposed operations from actual calls into enterprise systems. The skill harness, policy enforcement, credential service, and connector form this boundary.
Enterprise-system boundary: Separates AccuSec from external systems of record. External data is versioned, time-sensitive, permission-sensitive, and not assumed to be complete.
Model-provider boundary: Separates enterprise data and prompts from external or self-hosted model services. Routing and data handling policy are enforced here.
Persistence boundary: Separates transient runtime state from durable workflow, audit, context, and operational records.
Deployment boundary: Separates logical services from their physical placement on a laptop, appliance, customer Kubernetes environment, private cloud, or managed control plane.
Administrative boundary: Separates human roles that configure policy and privilege from agents that consume those controls.
Audit boundary: Separates mutable operational data from tamper-evident or immutable evidence required for investigation and compliance.
7. Data and State Vision
AccuSec processes heterogeneous enterprise data: identities, topology, inventory, configurations, metrics, events, logs, tickets, documents, prompts, plans, workflow state, tool results, secrets references, policies, approvals, and audit evidence. No single database model is appropriate for all of these forms. The architecture therefore defines logical data responsibilities first and chooses physical stores later.
7.1 Authoritative State
The target enterprise system remains authoritative for its managed resources unless an explicit replicated-control model is defined. AccuSec stores observations, normalized context, workflow state, intent, plans, and evidence; it does not silently become the source of truth for external infrastructure.
7.2 Temporal Context
Operational context is time-sensitive. Every plan SHOULD identify the observation time, source, freshness, and confidence of material facts. A plan created from stale context must be revalidated before execution.
7.3 Memory
Memory is divided into at least four logical classes: active task state, short-term conversational context, durable operational memory, and curated organizational knowledge. Memory does not bypass authorization. Retrieval permissions must be evaluated at query time, and sensitive data must not become broadly retrievable merely because it was embedded or summarized.
7.4 Audit Evidence
Audit evidence is append-oriented, integrity-protected, tenant-scoped, and independently queryable. It records identities, decisions, inputs, material context references, policy outcomes, approvals, tool calls, target responses, state transitions, and final outcomes. Sensitive values such as secrets are referenced or redacted rather than copied into logs.
7.5 Data Minimization and Classification
The platform MUST classify data by tenant, sensitivity, purpose, retention, residency, and model-usage eligibility. Only the minimum required data should be sent to a model or tool. Data handling decisions belong in enforceable policy, not only in prompts.
8. Deployment Vision
AccuSec must support a deployment continuum without creating different products with incompatible semantics. The logical architecture remains stable; service placement, scaling, isolation, and operational responsibility vary by edition.
Dimension
Basic / Desktop
Enterprise Private
Future Managed / Hybrid
Primary user
Individual cloud administrator
Teams across one or more enterprises or service-provider customers
Distributed enterprise teams with optional managed control services
Placement
Administrator workstation or local appliance
Customer-controlled Kubernetes/private cloud/on-premises environment
Split placement based on data, latency, trust, and operations policy
Service topology
Components may be co-located or embedded
Services scale independently and are highly available
Control and execution services may be separated across regions and sites
Tenancy
Single user or workspace
Multi-user and multi-tenant with strong isolation
Federated tenancy and delegated administration
Credentials
Local secure store or delegated identity
Enterprise vault/KMS, workload identity, short-lived credentials
Customer-owned secrets with brokered access
Data
Local by default
Customer-controlled persistence and retention
Policy-directed local, regional, or managed storage
Operations
Self-managed
Enterprise-operated or partner-operated
Shared operational responsibility
Deployment invariant A workflow, skill, policy, audit record, or connector must not change meaning merely because components are collapsed into one process for desktop deployment or distributed across clusters for enterprise deployment.

9. Autonomy and Risk Model
AccuSec does not treat autonomy as a binary product setting. Autonomy is granted per workflow, action, target, tenant, identity, and operating condition. The architecture supports progressive autonomy based on risk and evidence.
Level
Behavior
Typical examples
Required controls
A0 — Observe
Read, summarize, correlate, and explain without changing external state.
Inventory, health summaries, incident correlation.
Read authorization, data policy, source citations, audit.
A1 — Recommend
Create plans and commands but do not execute.
Remediation plan, upgrade proposal, capacity recommendation.
Plan validation, risk score, explanation, reviewer identity.
A2 — Approve each action
Execute only after explicit approval for each consequential step.
VM creation, cluster expansion, policy change.
Step-level approval, scoped credentials, pre/post checks.
A3 — Approve plan
Execute an approved bounded plan with controlled adaptation.
Standard maintenance workflow, validated deployment.
Plan scope, adaptation limits, checkpoints, rollback.
A4 — Policy-bounded autonomy
Execute pre-approved workflows when conditions and risk remain within policy.
Routine remediation, ticket-driven standard changes.
Strong policy, continuous verification, kill switch, anomaly escalation.
A5 — Exceptional autonomy
Reserved for narrow, proven, time-critical workflows.
Automatic containment of a known failure mode.
Extensive evidence, simulation, blast-radius limits, post-review.
10. Quality Attribute Priorities
When quality attributes conflict, the following ordering guides decisions for the initial Hybrid Cloud product. The ordering may vary for non-production or read-only workflows but must be explicit.
Security and tenant isolation — prevent unauthorized disclosure or action.
Correctness and safety — avoid incorrect, duplicate, destructive, or unverified operations.
Auditability and explainability — preserve evidence and human comprehension.
Recoverability — survive partial failure and restore a known workflow state.
Availability — remain usable and degrade predictably.
Interoperability and extensibility — integrate across heterogeneous enterprise environments.
Performance and responsiveness — provide interactive feedback while supporting long-running work.
Efficiency and cost — optimize model, compute, storage, and operator effort.
Implementation simplicity — reduce complexity where it does not compromise higher priorities.
10.1 Initial Architectural Targets
The following are directional targets for design evaluation, not final service-level objectives. Part II and component chapters will refine them.
Attribute
Initial target
Architectural implication
No hidden privileged action
Every external state change maps to an admitted task, authorized step, tool invocation, and audit event.
Correlation IDs and immutable execution evidence are mandatory.
Safe duplicate handling
Retries must not unintentionally repeat a completed state-changing operation.
Idempotency keys, external reconciliation, and step state are required.
Bounded blast radius
A task may operate only on explicitly scoped resources and limits.
Scope validation and per-step authorization are required.
Visible progress
Users can see task state, waiting conditions, approvals, failures, and recovery options.
Durable workflows and event-driven UI updates are required.
Model portability
At least two model providers or a provider-neutral interface can support core reasoning paths.
AI gateway and model abstraction are required.
Connector isolation
A failing or compromised connector cannot implicitly compromise the platform or other tenants.
Sandboxing, timeouts, network policy, and scoped credentials are required.
Forensic reconstruction
A reviewer can reconstruct a consequential operation without relying on volatile model context.
Durable context references, decisions, policy results, and tool outputs are required.
11. Explicit Non-Goals and Prohibited Shortcuts
AccuSec is not a general chatbot that happens to call infrastructure APIs.
AccuSec is not a single monolithic agent with unrestricted access to every tool and data source.
AccuSec does not use prompts as the sole mechanism for access control, compliance, tenancy, data protection, or workflow safety.
AccuSec does not treat vector retrieval as an authorization system or a source-of-truth database.
AccuSec does not assume a successful API response means the intended operational outcome occurred; postcondition verification is required where material.
AccuSec does not hide target-system errors behind confident natural-language responses.
AccuSec does not require every operation to use an LLM. Deterministic code, rules, queries, and workflows are preferred when they solve the problem reliably.
AccuSec does not centralize all customer data by default. Data placement follows deployment and policy requirements.
AccuSec does not allow domain agents or plugins to bypass the common execution, identity, policy, and audit controls.
AccuSec does not optimize for broad multi-domain coverage before proving the Hybrid Cloud wedge.
12. Architecture Decision Framework
Every significant design decision in later chapters should be evaluated using the following questions. The answer must be explicit; “the framework handles it” is not sufficient.
What is the component’s single primary responsibility, and what responsibilities are intentionally elsewhere?
Which identity is acting, and how is that identity propagated and verified?
What data enters, leaves, or persists, and what are its tenant, sensitivity, retention, and residency requirements?
Which system is authoritative for each material fact?
Where are policy decisions made, and where are they enforced?
Which interactions are synchronous, asynchronous, streamed, scheduled, or event-driven, and why?
What happens when the model, connector, broker, database, network, or target system fails?
How are retries made idempotent, and how is partial completion detected?
What evidence is produced for users, operators, security teams, and auditors?
How does the design work in both desktop and enterprise deployments?
How is the component versioned, extended, tested, and isolated?
Can deterministic logic replace model reasoning for any part of the design?
What is the blast radius of compromise or malfunction?
What observable metric proves the component is useful and trustworthy?
12.1 Architecture Decision Records
Material decisions SHOULD be captured as Architecture Decision Records containing: context, decision, alternatives, consequences, security impact, data impact, operational impact, compatibility impact, and review date. Examples include workflow engine selection, message semantics, graph storage, model gateway behavior, tenant isolation, secret delivery, MCP trust policy, and desktop-to-enterprise packaging.
13. Validation Strategy
The architecture will be validated through use cases with the design partner, not only through design review. At least twenty cloud administrators will be interviewed, and the first five use cases will be selected based on frequency, pain, trust requirement, demonstrability, and willingness to adopt.
Each use case should produce an architecture validation package containing:
User intent and business outcome.
Actors, identities, roles, and approval authorities.
Context sources and freshness requirements.
Plan and workflow graph.
Skills, tools, connectors, and target systems.
Policy decisions and enforcement points.
Synchronous and asynchronous interactions.
Durable state, events, retries, idempotency, and recovery behavior.
Data classification, retention, and model exposure.
Audit evidence and user-facing explanation.
Latency, cost, success rate, operator intervention, and trust feedback.
A component should not be added merely because it appears in the reference diagram. It must either satisfy a cross-cutting architectural requirement or enable a validated use case. Conversely, a use case must not bypass the architecture merely to create a faster demonstration.
14. Relationship to Part II — High-Level Logical Architecture
Part II converts this vision into the canonical high-level logical architecture. It explains every box, arrow, interaction type, trust boundary, and data boundary in the finalized diagram. Part II must demonstrate how the logical components collectively implement the principles and invariants in this chapter.
In particular, Part II will define:
User interfaces and request-admission paths.
AI orchestration responsibilities and durable task lifecycle.
Enterprise AI Engineers, system skills, skill harness, MCP client, and memory manager.
Platform services including context, observability, policy, security, audit, notifications, document intelligence, prompts, features, and usage metering.
Logical data stores and ownership boundaries.
Integration and connectivity through registries, gateways, event buses, queues, and webhooks.
AI gateway, model orchestration, provider boundaries, and data handling.
Identity, RBAC/ABAC, tenancy, privacy, and compliance boundaries.
Platform foundation responsibilities.
Synchronous, asynchronous, streaming, scheduled, approval, and callback interactions.
Part I acceptance rule A Part II design is acceptable only if it preserves the separation between probabilistic reasoning and deterministic authority, supports durable governed tasks, and makes every consequential operation identity-bound, policy-enforced, observable, recoverable, and auditable.

Appendix A — Canonical Vocabulary
Term
Definition
Enterprise AI Operating System
The shared runtime and control plane that enables governed Enterprise AI Engineers across enterprise domains.
Enterprise AI Engineer
A domain-bounded agentic capability that converts intent into governed operational outcomes.
Agent
A runtime reasoning participant with a defined role, state, tools, policies, and termination conditions.
Agent loop
The controlled cycle of observe, reason, plan, act, evaluate, and continue or stop.
Skill
A reusable declared capability that performs a bounded operation or computation.
Skill harness
The deterministic control envelope that validates, authorizes, executes, observes, retries, and audits skills.
Tool
A callable operation exposed by an API, MCP server, internal service, script, or connector.
MCP
A protocol used to expose and consume model-oriented tools, resources, and prompts; it does not by itself establish trust or authorization.
Operational context
The current and historical facts needed to reason about and safely operate enterprise systems.
Operational memory
Durable, curated knowledge derived from prior tasks, outcomes, environments, and organizational practices.
Task
A durable unit of requested work with identity, scope, state, policy, history, and outcome.
Workflow
A stateful graph of steps, decisions, waits, approvals, tool calls, validations, and recovery paths.
Plan
A proposed workflow instance or ordered set of typed actions designed to achieve an intent.
Guardrail
A deterministic constraint or validation intended to prevent or contain unacceptable behavior.
Policy
An authoritative rule governing access, execution, data handling, risk, approval, or compliance.
Evidence
Persistent information sufficient to explain and reconstruct a decision or operation.
Trust boundary
A boundary across which identity, authority, data sensitivity, or component trust assumptions change.
Data boundary
A boundary that defines ownership, tenancy, classification, persistence, access, or movement of data.
Human-in-the-loop
A workflow state in which a human reviews, approves, rejects, modifies, or escalates a decision or action.
Basic Edition
A logically compatible single-user or small-workspace deployment in which services may be collapsed locally.
Enterprise Edition
A distributed, multi-user, multi-tenant, highly available deployment under enterprise control.
Appendix B — Architecture Invariants Checklist
☐ No external state-changing operation without a verified acting identity.
☐ No privileged operation based only on model output.
☐ No cross-tenant data or memory access without explicit authorized sharing.
☐ No tool execution without registration, validation, policy evaluation, and audit correlation.
☐ No durable workflow state stored only in chat history or model context.
☐ No retry of a state-changing step without idempotency or reconciliation logic.
☐ No secret value persisted in prompts, ordinary logs, embeddings, or audit payloads.
☐ No model provider receives data prohibited by tenant or classification policy.
☐ No high-impact plan executes without the required approval state.
☐ No completed operation is reported successful without sufficient outcome verification.
☐ No plugin, agent, connector, or MCP server bypasses the common security and execution controls.
☐ No architecture decision depends on a single vendor unless explicitly accepted and recorded.
