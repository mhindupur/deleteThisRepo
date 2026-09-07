# AccuSec AWS inventory role

AccuSec does not take long-lived AWS keys in chat or in MySQL. You create a
**read-only** IAM role in the target account, then pass AccuSec a **secret
reference** that tells the AWS connector how to assume that role (or which
local AWS CLI profile to use).

## Role to create

Create **`AccuSecInventoryReader`** in the AWS account you want to inventory.

| Piece | File |
|---|---|
| Permissions (enumerate + hydrate catalog types) | [`AccuSecInventoryReader-policy.json`](./AccuSecInventoryReader-policy.json) |
| Trust (your IAM user/role may assume it) | [`AccuSecInventoryReader-trust.json`](./AccuSecInventoryReader-trust.json) |

Replace `ACCOUNT_ID` and `DEVELOPER_IAM_USER` in the trust policy with the
principal that already works for `aws sts get-caller-identity` on your laptop
(your IAM user, SSO role, or a CI workload role). Keep `ExternalId` as
`accusec-local` unless you choose another value and pass the same value to
AccuSec.

```bash
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
aws iam create-role \
  --role-name AccuSecInventoryReader \
  --assume-role-policy-document file://integration/connectors/hybrid-cloud/aws/iam/AccuSecInventoryReader-trust.json
aws iam put-role-policy \
  --role-name AccuSecInventoryReader \
  --policy-name AccuSecInventoryReader \
  --policy-document file://integration/connectors/hybrid-cloud/aws/iam/AccuSecInventoryReader-policy.json
```

This role is **observe-only**. It cannot stop instances or change AWS state.
Writes stay on a separate operator role later.

Optional but recommended: turn on **Resource Explorer** (aggregator index, often
in `us-east-1`) so AccuSec can list resource types beyond the first catalog.
If Resource Explorer is not enabled, sync still hydrates catalog types via
Cloud Control / `Describe*` and records skipped enumerator errors.

## How to pass the role into AccuSec

Never put the role ARN or keys in the intent string. Register a named secret,
then attach that **secret-ref** to a provider connection.

### 1. Store how AccuSec authenticates (local secrets file)

Default file: `~/.accusec/secrets.json` (mode `600`). Override with
`ACCUSEC_SECRETS_PATH`.

**Preferred — assume the inventory role using your existing AWS profile:**

```bash
pip install -e ".[aws]"
accusec secrets put aws/operator \
  --auth-mode assume-role \
  --role-arn arn:aws:iam::123456789012:role/AccuSecInventoryReader \
  --external-id accusec-local \
  --profile default
```

`--profile` is the AWS CLI profile that is **trusted to assume** the role
(your user/SSO). AccuSec calls `sts:AssumeRole` inside the connector and never
sends the resulting keys to the model or audit log.

**Local-only — use the profile as the account identity** (no assume-role; the
profile itself must already have the inventory permissions):

```bash
accusec secrets put aws/dev --auth-mode profile --profile default
```

**Avoid** `--auth-mode access-key` except for throwaway labs. If you must:

```bash
accusec secrets put aws/lab \
  --auth-mode access-key \
  --access-key-id AKIA... \
  --secret-access-key '...'
```

List registered names (no secret values):

```bash
accusec secrets list
```

### 2. Connect the account (STS must match)

```bash
accusec provider connect aws \
  --account 123456789012 \
  --regions us-east-1,us-west-2 \
  --secret-ref aws/operator
```

AccuSec stores the connection in MySQL (`provider_connections`) with
`secret_ref` only. The connector then calls `GetCallerIdentity` and **fails
closed** if the STS account is not `--account`.

```bash
accusec provider status
accusec provider sync --region us-east-1
```

## What AccuSec stores

| Store | Contents |
|---|---|
| `~/.accusec/secrets.json` | Auth mode, role ARN, profile, optional keys |
| MySQL `provider_connections` | account, regions, `secret-ref:aws/operator` — not keys |
| MySQL `entities` | Observations from sync (`last_observed_at`, `source`) |
