# AWS Connector

**Layer:** Integration  
**Provider:** AWS

Controlled AWS API boundary. The Hybrid Cloud Engineer and AWS MCP server
must not embed credentials or call AWS without this connector. `boto3` lives
only here.

## Connect (developer)

Create IAM role **`AccuSecInventoryReader`** and pass it as a secret reference.
Do not put keys in the intent string. Full steps:

[`iam/README.md`](./iam/README.md)

```bash
pip install -e ".[aws]"
accusec secrets put aws/operator \
  --auth-mode assume-role \
  --role-arn arn:aws:iam::ACCOUNT:role/AccuSecInventoryReader \
  --external-id accusec-local \
  --profile default
accusec provider connect aws --account ACCOUNT --regions us-east-1 --secret-ref aws/operator
accusec provider sync --region us-east-1
```

STS `GetCallerIdentity` must match `--account` or connect fails closed.

## Responsibilities

- Workload identity or assumed-role credentials via Secrets Manager (never env dumps into prompts)
- Region and account allowlisting from Scope
- Pagination, throttling, retries, error translation
- Normalize AWS resources to AccuSec entity records
- Enumerate (Resource Explorer / Cloud Control) and hydrate catalog types (`DescribeInstances`)

## Fixture mode

Tests and `ACCUSEC_USE_FIXTURES=1` use in-memory EC2 fixtures. No live AWS call.
