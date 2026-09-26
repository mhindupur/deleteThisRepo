"""AccuSec-authoritative connector registration and sync runs (not AWS inventory)."""

from __future__ import annotations

import json
from typing import Any

from accusec.memory.entity.store import mysql_config
from accusec.shared.domain.models import (
    AuditEvent,
    EndpointAccessIdentity,
    ProviderConnection,
    SyncRun,
    Task,
    utcnow,
)

DDL = [
    """
    CREATE TABLE IF NOT EXISTS provider_connections (
      connection_id VARCHAR(64) NOT NULL PRIMARY KEY,
      provider VARCHAR(32) NOT NULL,
      tenant_id VARCHAR(64) NOT NULL,
      workspace_id VARCHAR(64) NOT NULL,
      account_id VARCHAR(32) NOT NULL,
      regions_json JSON NOT NULL,
      secret_ref VARCHAR(255) NOT NULL,
      status VARCHAR(32) NOT NULL,
      last_sync_at VARCHAR(64) NULL,
      last_error VARCHAR(1024) NULL,
      created_by VARCHAR(128) NOT NULL,
      caller_arn VARCHAR(512) NULL,
      endpoint_id VARCHAR(64) NULL,
      project_id VARCHAR(64) NOT NULL DEFAULT 'project-0',
      datacenter_id VARCHAR(64) NOT NULL DEFAULT 'dc-aws',
      UNIQUE KEY uq_provider_account_workspace (provider, account_id, workspace_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sync_runs (
      sync_id VARCHAR(64) NOT NULL PRIMARY KEY,
      connection_id VARCHAR(64) NOT NULL,
      provider VARCHAR(32) NOT NULL,
      account_id VARCHAR(32) NOT NULL,
      region VARCHAR(32) NOT NULL,
      mode VARCHAR(32) NOT NULL,
      status VARCHAR(32) NOT NULL,
      started_at VARCHAR(64) NOT NULL,
      finished_at VARCHAR(64) NULL,
      upserted INT NOT NULL DEFAULT 0,
      missing_count INT NOT NULL DEFAULT 0,
      enumerated_types_json JSON NOT NULL,
      skipped_json JSON NOT NULL,
      error VARCHAR(1024) NULL,
      INDEX idx_sync_connection (connection_id, started_at)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS entity_type_coverage (
      connection_id VARCHAR(64) NOT NULL,
      entity_type VARCHAR(128) NOT NULL,
      provider_type VARCHAR(128) NOT NULL,
      region VARCHAR(32) NOT NULL,
      depth VARCHAR(32) NOT NULL,
      resource_count INT NOT NULL DEFAULT 0,
      last_seen_at VARCHAR(64) NOT NULL,
      PRIMARY KEY (connection_id, entity_type, region)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tenants (
      tenant_id VARCHAR(64) NOT NULL PRIMARY KEY,
      display_name VARCHAR(255) NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS projects (
      project_id VARCHAR(64) NOT NULL PRIMARY KEY,
      tenant_id VARCHAR(64) NOT NULL,
      display_name VARCHAR(255) NOT NULL,
      kind VARCHAR(32) NOT NULL DEFAULT 'project'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS datacenters (
      datacenter_id VARCHAR(64) NOT NULL PRIMARY KEY,
      tenant_id VARCHAR(64) NOT NULL,
      project_id VARCHAR(64) NOT NULL,
      workspace_id VARCHAR(64) NOT NULL,
      display_name VARCHAR(255) NOT NULL,
      endpoint_id VARCHAR(64) NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS endpoint_access_identities (
      endpoint_identity_id VARCHAR(64) NOT NULL PRIMARY KEY,
      tenant_id VARCHAR(64) NOT NULL,
      endpoint_id VARCHAR(64) NOT NULL,
      provider_type VARCHAR(32) NOT NULL,
      identity_type VARCHAR(32) NOT NULL,
      secret_ref VARCHAR(255) NOT NULL,
      status VARCHAR(32) NOT NULL,
      display_name VARCHAR(255) NOT NULL,
      last_verified_at VARCHAR(64) NULL,
      INDEX idx_eai_endpoint (endpoint_id, status)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tasks (
      task_id VARCHAR(64) NOT NULL PRIMARY KEY,
      state VARCHAR(32) NOT NULL,
      task_json JSON NOT NULL,
      updated_at VARCHAR(64) NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS approvals (
      approval_id VARCHAR(64) NOT NULL PRIMARY KEY,
      plan_id VARCHAR(64) NOT NULL,
      plan_version INT NOT NULL,
      status VARCHAR(32) NOT NULL,
      requester VARCHAR(128) NOT NULL,
      approver VARCHAR(128) NULL,
      task_id VARCHAR(64) NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_events (
      event_id VARCHAR(64) NOT NULL PRIMARY KEY,
      event_type VARCHAR(64) NOT NULL,
      tenant_id VARCHAR(64) NOT NULL,
      principal_id VARCHAR(128) NOT NULL,
      operation_id VARCHAR(128) NULL,
      task_id VARCHAR(64) NULL,
      correlation_id VARCHAR(64) NULL,
      payload_json JSON NOT NULL,
      timestamp VARCHAR(64) NOT NULL,
      INDEX idx_audit_corr (correlation_id)
    )
    """,
]


class ControlPlaneStore:
    def __init__(self, database: str | None = None) -> None:
        import pymysql

        self._cfg = mysql_config(database)
        self.database = self._cfg["database"]
        self._conn = pymysql.connect(**self._cfg)
        with self._conn.cursor() as cur:
            for stmt in DDL:
                cur.execute(stmt)
            self._migrate(cur)
        self._conn.commit()
        self.ensure_desktop_org()

    def _migrate(self, cur) -> None:
        cur.execute(
            """
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'provider_connections'
            """
        )
        cols = {row["COLUMN_NAME"] for row in cur.fetchall()}
        if "endpoint_id" not in cols:
            cur.execute("ALTER TABLE provider_connections ADD COLUMN endpoint_id VARCHAR(64) NULL")
        if "project_id" not in cols:
            cur.execute("ALTER TABLE provider_connections ADD COLUMN project_id VARCHAR(64) NOT NULL DEFAULT 'project-0'")
        if "datacenter_id" not in cols:
            cur.execute("ALTER TABLE provider_connections ADD COLUMN datacenter_id VARCHAR(64) NOT NULL DEFAULT 'dc-aws'")

    def ensure_desktop_org(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO tenants (tenant_id, display_name) VALUES (%s, %s)",
                ("tenant-1", "Desktop Tenant"),
            )
            cur.execute(
                "INSERT IGNORE INTO projects (project_id, tenant_id, display_name, kind) VALUES (%s, %s, %s, %s)",
                ("project-0", "tenant-1", "Project 0", "project0"),
            )
            cur.execute(
                """
                INSERT IGNORE INTO datacenters
                (datacenter_id, tenant_id, project_id, workspace_id, display_name, endpoint_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                ("dc-aws", "tenant-1", "project-0", "aws-prod", "AWS Datacenter", None),
            )
        self._conn.commit()

    def upsert_connection(self, conn: ProviderConnection) -> None:
        sql = """
            INSERT INTO provider_connections (
                connection_id, provider, tenant_id, workspace_id, account_id,
                regions_json, secret_ref, status, last_sync_at, last_error,
                created_by, caller_arn, endpoint_id, project_id, datacenter_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            AS new
            ON DUPLICATE KEY UPDATE
                regions_json = new.regions_json,
                secret_ref = new.secret_ref,
                status = new.status,
                last_sync_at = new.last_sync_at,
                last_error = new.last_error,
                caller_arn = new.caller_arn,
                endpoint_id = new.endpoint_id,
                project_id = new.project_id,
                datacenter_id = new.datacenter_id
        """
        if not conn.endpoint_id:
            conn.endpoint_id = "ep-aws"
        with self._conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    conn.connection_id,
                    conn.provider,
                    conn.tenant_id,
                    conn.workspace_id,
                    conn.account_id,
                    json.dumps(conn.regions),
                    conn.secret_ref,
                    conn.status,
                    conn.last_sync_at.isoformat() if hasattr(conn.last_sync_at, "isoformat") else conn.last_sync_at,
                    conn.last_error,
                    conn.created_by,
                    conn.caller_arn,
                    conn.endpoint_id,
                    conn.project_id,
                    conn.datacenter_id,
                ),
            )
        self._conn.commit()

    def get_connection(self, connection_id: str) -> ProviderConnection | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM provider_connections WHERE connection_id = %s",
                (connection_id,),
            )
            row = cur.fetchone()
        return self._row_to_connection(row) if row else None

    def find_connection(self, *, provider: str, account_id: str, workspace_id: str) -> ProviderConnection | None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM provider_connections
                WHERE provider = %s AND account_id = %s AND workspace_id = %s
                """,
                (provider, account_id, workspace_id),
            )
            row = cur.fetchone()
        return self._row_to_connection(row) if row else None

    def list_connections(self, provider: str | None = None) -> list[ProviderConnection]:
        sql = "SELECT * FROM provider_connections"
        args: tuple[Any, ...] = ()
        if provider:
            sql += " WHERE provider = %s"
            args = (provider,)
        sql += " ORDER BY provider, account_id"
        with self._conn.cursor() as cur:
            cur.execute(sql, args)
            rows = cur.fetchall()
        return [self._row_to_connection(r) for r in rows]

    def active_aws(self) -> ProviderConnection | None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM provider_connections
                WHERE provider = 'aws' AND status = 'active'
                ORDER BY last_sync_at IS NULL, last_sync_at DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
        return self._row_to_connection(row) if row else None

    def save_sync(self, run: SyncRun) -> None:
        sql = """
            INSERT INTO sync_runs (
                sync_id, connection_id, provider, account_id, region, mode,
                status, started_at, finished_at, upserted, missing_count,
                enumerated_types_json, skipped_json, error
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            AS new
            ON DUPLICATE KEY UPDATE
                status = new.status,
                finished_at = new.finished_at,
                upserted = new.upserted,
                missing_count = new.missing_count,
                enumerated_types_json = new.enumerated_types_json,
                skipped_json = new.skipped_json,
                error = new.error
        """
        with self._conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    run.sync_id,
                    run.connection_id,
                    run.provider,
                    run.account_id,
                    run.region,
                    run.mode,
                    run.status,
                    run.started_at.isoformat(),
                    run.finished_at.isoformat() if run.finished_at else None,
                    run.upserted,
                    run.missing,
                    json.dumps(run.enumerated_types),
                    json.dumps(run.skipped),
                    run.error,
                ),
            )
        self._conn.commit()

    def recent_syncs(self, connection_id: str, limit: int = 10) -> list[SyncRun]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM sync_runs WHERE connection_id = %s
                ORDER BY started_at DESC LIMIT %s
                """,
                (connection_id, limit),
            )
            rows = cur.fetchall()
        return [self._row_to_sync(r) for r in rows]

    def record_coverage(
        self,
        *,
        connection_id: str,
        entity_type: str,
        provider_type: str,
        region: str,
        depth: str,
        resource_count: int,
    ) -> None:
        sql = """
            INSERT INTO entity_type_coverage (
                connection_id, entity_type, provider_type, region, depth,
                resource_count, last_seen_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            AS new
            ON DUPLICATE KEY UPDATE
                depth = new.depth,
                resource_count = new.resource_count,
                last_seen_at = new.last_seen_at,
                provider_type = new.provider_type
        """
        with self._conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    connection_id,
                    entity_type,
                    provider_type,
                    region,
                    depth,
                    resource_count,
                    utcnow().isoformat(),
                ),
            )
        self._conn.commit()

    def coverage_for(self, connection_id: str) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT entity_type, provider_type, region, depth, resource_count, last_seen_at
                FROM entity_type_coverage WHERE connection_id = %s
                ORDER BY region, entity_type
                """,
                (connection_id,),
            )
            return list(cur.fetchall())

    def org_snapshot(self) -> dict[str, Any]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT * FROM tenants WHERE tenant_id = %s", ("tenant-1",))
            tenant = cur.fetchone() or {"tenant_id": "tenant-1", "display_name": "Desktop Tenant"}
            cur.execute("SELECT * FROM projects WHERE project_id = %s", ("project-0",))
            project = cur.fetchone() or {"project_id": "project-0", "display_name": "Project 0"}
            cur.execute("SELECT * FROM datacenters WHERE datacenter_id = %s", ("dc-aws",))
            datacenter = cur.fetchone() or {
                "datacenter_id": "dc-aws",
                "workspace_id": "aws-prod",
                "display_name": "AWS Datacenter",
            }
        return {
            "tenant_id": tenant["tenant_id"],
            "tenant_name": tenant["display_name"],
            "project_id": project["project_id"],
            "project_name": project["display_name"],
            "datacenter_id": datacenter["datacenter_id"],
            "datacenter_name": datacenter["display_name"],
            "workspace_id": datacenter["workspace_id"],
        }

    def upsert_identity(self, identity: EndpointAccessIdentity) -> None:
        sql = """
            INSERT INTO endpoint_access_identities (
                endpoint_identity_id, tenant_id, endpoint_id, provider_type,
                identity_type, secret_ref, status, display_name, last_verified_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            AS new
            ON DUPLICATE KEY UPDATE
                secret_ref = new.secret_ref,
                status = new.status,
                display_name = new.display_name,
                last_verified_at = new.last_verified_at
        """
        verified = identity.last_verified_at
        with self._conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    identity.endpoint_identity_id,
                    identity.tenant_id,
                    identity.endpoint_id,
                    identity.provider_type,
                    identity.identity_type,
                    identity.secret_ref,
                    identity.status,
                    identity.display_name,
                    verified.isoformat() if hasattr(verified, "isoformat") else verified,
                ),
            )
        self._conn.commit()

    def list_identities(
        self,
        *,
        tenant_id: str | None = None,
        endpoint_id: str | None = None,
    ) -> list[EndpointAccessIdentity]:
        sql = "SELECT * FROM endpoint_access_identities WHERE 1=1"
        args: list[Any] = []
        if tenant_id:
            sql += " AND tenant_id = %s"
            args.append(tenant_id)
        if endpoint_id:
            sql += " AND endpoint_id = %s"
            args.append(endpoint_id)
        sql += " ORDER BY identity_type, display_name"
        with self._conn.cursor() as cur:
            cur.execute(sql, args)
            rows = cur.fetchall()
        return [self._row_to_identity(row) for row in rows]

    def get_identity(self, endpoint_identity_id: str) -> EndpointAccessIdentity | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM endpoint_access_identities WHERE endpoint_identity_id = %s",
                (endpoint_identity_id,),
            )
            row = cur.fetchone()
        return self._row_to_identity(row) if row else None

    def ensure_endpoint_identity(
        self,
        *,
        tenant_id: str,
        endpoint_id: str,
        secret_ref: str,
        identity_type: str = "OPERATOR",
        display_name: str = "Desktop AWS operator",
    ) -> EndpointAccessIdentity:
        for item in self.list_identities(tenant_id=tenant_id, endpoint_id=endpoint_id):
            if item.identity_type == identity_type:
                if item.secret_ref != secret_ref or item.display_name != display_name:
                    item.secret_ref = secret_ref
                    item.display_name = display_name
                    item.status = "active"
                    self.upsert_identity(item)
                return item
        identity = EndpointAccessIdentity(
            tenant_id=tenant_id,
            endpoint_id=endpoint_id,
            identity_type=identity_type,
            secret_ref=secret_ref,
            display_name=display_name,
            last_verified_at=utcnow(),
        )
        self.upsert_identity(identity)
        return identity

    def save_task(self, task: Task) -> None:
        sql = """
            INSERT INTO tasks (task_id, state, task_json, updated_at)
            VALUES (%s, %s, %s, %s) AS new
            ON DUPLICATE KEY UPDATE
                state = new.state,
                task_json = new.task_json,
                updated_at = new.updated_at
        """
        with self._conn.cursor() as cur:
            cur.execute(
                sql,
                (task.task_id, task.state.value, task.model_dump_json(), utcnow().isoformat()),
            )
        self._conn.commit()

    def get_task(self, task_id: str) -> Task | None:
        with self._conn.cursor() as cur:
            cur.execute("SELECT task_json FROM tasks WHERE task_id = %s", (task_id,))
            row = cur.fetchone()
        if not row:
            return None
        payload = row["task_json"]
        if isinstance(payload, (bytes, bytearray)):
            payload = payload.decode()
        if isinstance(payload, dict):
            return Task.model_validate(payload)
        return Task.model_validate_json(payload)

    def save_approval(self, approval_id: str, record: dict[str, Any]) -> None:
        sql = """
            INSERT INTO approvals (
                approval_id, plan_id, plan_version, status, requester, approver, task_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s) AS new
            ON DUPLICATE KEY UPDATE
                status = new.status,
                approver = new.approver,
                task_id = new.task_id
        """
        with self._conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    approval_id,
                    record["plan_id"],
                    int(record["version"]),
                    record["status"],
                    record["requester"],
                    record.get("approver"),
                    record.get("task_id"),
                ),
            )
        self._conn.commit()

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        with self._conn.cursor() as cur:
            cur.execute("SELECT * FROM approvals WHERE approval_id = %s", (approval_id,))
            row = cur.fetchone()
        if not row:
            return None
        return {
            "plan_id": row["plan_id"],
            "version": int(row["plan_version"]),
            "status": row["status"],
            "requester": row["requester"],
            "approver": row.get("approver"),
            "task_id": row.get("task_id"),
        }

    def save_audit(self, event: AuditEvent) -> None:
        sql = """
            INSERT INTO audit_events (
                event_id, event_type, tenant_id, principal_id, operation_id,
                task_id, correlation_id, payload_json, timestamp
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            AS new
            ON DUPLICATE KEY UPDATE payload_json = new.payload_json
        """
        with self._conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    event.event_id,
                    event.event_type,
                    event.tenant_id,
                    event.principal_id,
                    event.operation_id,
                    event.task_id,
                    event.correlation_id,
                    json.dumps(event.payload),
                    event.timestamp.isoformat() if hasattr(event.timestamp, "isoformat") else event.timestamp,
                ),
            )
        self._conn.commit()

    def _row_to_identity(self, row: dict[str, Any]) -> EndpointAccessIdentity:
        return EndpointAccessIdentity(
            endpoint_identity_id=row["endpoint_identity_id"],
            tenant_id=row["tenant_id"],
            endpoint_id=row["endpoint_id"],
            provider_type=row["provider_type"],
            identity_type=row["identity_type"],
            secret_ref=row["secret_ref"],
            status=row["status"],
            display_name=row["display_name"],
            last_verified_at=row.get("last_verified_at"),
        )

    def _row_to_connection(self, row: dict[str, Any]) -> ProviderConnection:
        regions = row["regions_json"]
        if isinstance(regions, str):
            regions = json.loads(regions)
        last_sync = row.get("last_sync_at")
        return ProviderConnection(
            connection_id=row["connection_id"],
            provider=row["provider"],
            tenant_id=row["tenant_id"],
            workspace_id=row["workspace_id"],
            account_id=row["account_id"],
            regions=list(regions or []),
            secret_ref=row["secret_ref"],
            status=row["status"],
            last_sync_at=last_sync,
            last_error=row.get("last_error"),
            created_by=row["created_by"],
            caller_arn=row.get("caller_arn"),
            endpoint_id=row.get("endpoint_id"),
            project_id=row.get("project_id") or "project-0",
            datacenter_id=row.get("datacenter_id") or "dc-aws",
        )

    def _row_to_sync(self, row: dict[str, Any]) -> SyncRun:
        types = row["enumerated_types_json"]
        skipped = row["skipped_json"]
        if isinstance(types, str):
            types = json.loads(types)
        if isinstance(skipped, str):
            skipped = json.loads(skipped)
        return SyncRun(
            sync_id=row["sync_id"],
            connection_id=row["connection_id"],
            provider=row["provider"],
            account_id=row["account_id"],
            region=row["region"],
            mode=row["mode"],
            status=row["status"],
            started_at=row["started_at"],
            finished_at=row.get("finished_at"),
            upserted=row["upserted"],
            missing=row["missing_count"],
            enumerated_types=list(types or []),
            skipped=list(skipped or []),
            error=row.get("error"),
        )
