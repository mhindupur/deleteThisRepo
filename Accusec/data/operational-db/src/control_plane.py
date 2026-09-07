"""AccuSec-authoritative connector registration and sync runs (not AWS inventory)."""

from __future__ import annotations

import json
from typing import Any

from accusec.memory.entity.store import mysql_config
from accusec.shared.domain.models import ProviderConnection, SyncRun, utcnow

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
        self._conn.commit()

    def upsert_connection(self, conn: ProviderConnection) -> None:
        sql = """
            INSERT INTO provider_connections (
                connection_id, provider, tenant_id, workspace_id, account_id,
                regions_json, secret_ref, status, last_sync_at, last_error,
                created_by, caller_arn
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            AS new
            ON DUPLICATE KEY UPDATE
                regions_json = new.regions_json,
                secret_ref = new.secret_ref,
                status = new.status,
                last_sync_at = new.last_sync_at,
                last_error = new.last_error,
                caller_arn = new.caller_arn
        """
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
