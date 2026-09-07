# Collectors

**Layer:** Integration

Polling and on-demand inventory collectors. Collectors must not import vendor
SDKs (`boto3`, Azure SDK). They call registered MCP tools through the Skill
Harness; the provider connector talks to the cloud.

## AWS inventory (this slice)

`InventoryCollector.sync(connection, region)`:

1. Policy check `inventory.sync` for the account/region
2. Enumerate via `aws.resourceexplorer.search` (Cloud Control fallback in the connector)
3. Hydrate catalog types via `aws.ec2.describe_instances` (more hydrators later)
4. Upsert MySQL `entities` with `last_observed_at`, `source`, `last_sync_id`
5. Mark previously synced rows not seen in this run as `lifecycle_state=missing`
6. Record `sync_runs` and `entity_type_coverage`

AWS remains source of truth. AccuSec stores observations.

Connect a real account (role + secret-ref) before sync:

See [`../connectors/hybrid-cloud/aws/iam/README.md`](../connectors/hybrid-cloud/aws/iam/README.md).
