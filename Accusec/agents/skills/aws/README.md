# AWS System Skills

**Layer:** Agent Framework  
**Provider:** AWS

Versioned skills that describe **how** to accomplish an AWS domain task.
Skills select and sequence tools; they do not talk to AWS APIs themselves.

## Status

Scaffold — implementation pending.

## Initial skill set (A0)

| Skill id | Outcome | Tools used |
|---|---|---|
| `aws.identity.describe` | Confirm caller account/arn/region | `aws.sts.get_caller_identity` |
| `aws.compute.instance.list` | List in-scope EC2 instances | `aws.ec2.describe_instances` |
| `aws.compute.instance.diagnose` | Explain instance health / CPU / status checks | `aws.ec2.describe_instances`, `aws.ec2.describe_instance_status`, `aws.cloudwatch.get_metric_statistics` |
| `aws.eks.cluster.diagnose` | Explain EKS cluster / node health (after A0.2) | EKS + EC2 + CloudWatch read tools |

## Later (A1 / A2)

- `aws.compute.instance.restart.plan` — plan only
- `aws.compute.instance.restart.execute` — harness + approval + postcondition

Each skill MUST declare: inputs, outputs, side effects, risk, required
operation ids, required tools, expected postconditions.

## Planned contents

- `src/` — skill manifests and any deterministic skill logic
- `tests/` — schema, entitlement, and A0 fixture tests
