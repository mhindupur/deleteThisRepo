# Operational Database

**Layer:** Data Layer

Local first store is **MySQL** (`accusec`). PostgreSQL remains an option for later Enterprise packaging; this slice does not use SQLite.

## Local database

| Name | Use |
|---|---|
| `accusec` | CLI / app |
| `accusec_test` | pytest |

User: `accusec` / password: `Manju123~*` on `127.0.0.1:3306`.

```bash
mysql -uroot < data/operational-db/schema.sql
mysql -uaccusec -p'Manju123~*' accusec -e "SELECT display_name, instance_type, region FROM entities;"
accusec --inspect-db
```

Override with `ACCUSEC_MYSQL_HOST`, `ACCUSEC_MYSQL_PORT`, `ACCUSEC_MYSQL_USER`, `ACCUSEC_MYSQL_PASSWORD`, `ACCUSEC_MYSQL_DATABASE`.

Control-plane tables (AccuSec source of truth, not AWS inventory): `provider_connections`, `sync_runs`, `entity_type_coverage`. AWS observations stay in `entities` with `last_observed_at` and `last_sync_id`.
