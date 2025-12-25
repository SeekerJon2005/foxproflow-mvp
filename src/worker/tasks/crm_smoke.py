# -*- coding: utf-8 -*-
# file: src/worker/tasks/crm_smoke.py
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

from celery import shared_task

log = logging.getLogger(__name__)


def _db_dsn() -> str:
    dsn = (os.getenv("DATABASE_URL") or "").strip()
    if dsn:
        return dsn
    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow")
    auth = f":{pwd}" if pwd else ""
    return f"postgresql://{user}{auth}@{host}:{port}/{db}"


def _pg():
    dsn = _db_dsn()
    try:
        import psycopg  # psycopg3
        return psycopg.connect(dsn)
    except Exception:
        import psycopg2 as psycopg  # fallback psycopg2
        return psycopg.connect(dsn)


def _to_regclass(cur, rel: str) -> bool:
    cur.execute("SELECT to_regclass(%s) IS NOT NULL;", (rel,))
    return bool(cur.fetchone()[0])


def _col_exists(cur, schema: str, table: str, col: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS(
          SELECT 1
          FROM information_schema.columns
          WHERE table_schema=%s AND table_name=%s AND column_name=%s
        );
        """,
        (schema, table, col),
    )
    return bool(cur.fetchone()[0])


def _get_col_udt(cur, schema: str, table: str, col: str) -> Optional[str]:
    cur.execute(
        """
        SELECT udt_name
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s AND column_name=%s
        """,
        (schema, table, col),
    )
    row = cur.fetchone()
    return str(row[0]) if row and row[0] is not None else None


def _get_col_default(cur, schema: str, table: str, col: str) -> Optional[str]:
    cur.execute(
        """
        SELECT column_default
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s AND column_name=%s
        """,
        (schema, table, col),
    )
    row = cur.fetchone()
    return str(row[0]) if row and row[0] is not None else None


def _get_notnull_no_default(cur, schema: str, table: str) -> List[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s
          AND is_nullable='NO'
          AND (column_default IS NULL OR btrim(column_default)='')
        ORDER BY ordinal_position;
        """,
        (schema, table),
    )
    return [str(r[0]) for r in (cur.fetchall() or [])]


@shared_task(name="crm.smoke.db_contract_v2")
def crm_smoke_db_contract_v2() -> Dict[str, Any]:
    """
    CRM DB-contract smoke v2 (matches current schema):

    Required objects (P0):
      - crm.tenants (table)
      - crm.leads (table)
      - crm.leads_trial_candidates_v (view)

    Checks:
      1) Existence via to_regclass
      2) tenants.id type=uuid and has default
      3) leads has core columns: id, status, payload, created_at, updated_at
      4) Transactional insert into crm.leads (rollback)
      5) View is queryable (count(*))

    Notes:
      - Current crm.tenants has only (id uuid default, created_at). No name/title fields.
      - So we do not try to insert tenants rows (no need for leads insert in current schema).
    """
    t0 = time.time()
    checks: Dict[str, Any] = {}
    details: Dict[str, Any] = {}
    missing: List[str] = []

    required = [
        "crm.tenants",
        "crm.leads",
        "crm.leads_trial_candidates_v",
    ]

    with _pg() as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            # 1) Existence
            for rel in required:
                ok = _to_regclass(cur, rel)
                checks[rel] = ok
                if not ok:
                    missing.append(rel)

            if missing:
                conn.rollback()
                return {
                    "ok": False,
                    "service": "crm",
                    "db_contract": False,
                    "missing": missing,
                    "checks": checks,
                    "details": details,
                    "elapsed_ms": int((time.time() - t0) * 1000),
                }

            # 2) tenants.id contract
            tenants_id_udt = _get_col_udt(cur, "crm", "tenants", "id")
            tenants_id_def = _get_col_default(cur, "crm", "tenants", "id")
            details["tenants_id_udt"] = tenants_id_udt
            details["tenants_id_default"] = tenants_id_def
            checks["crm.tenants.id_is_uuid"] = (tenants_id_udt == "uuid")
            checks["crm.tenants.id_has_default"] = bool(tenants_id_def)

            # 3) leads core columns
            for col in ("id", "status", "payload", "created_at", "updated_at"):
                checks[f"crm.leads.has_{col}"] = _col_exists(cur, "crm", "leads", col)

            leads_nn = _get_notnull_no_default(cur, "crm", "leads")
            tenants_nn = _get_notnull_no_default(cur, "crm", "tenants")
            details["leads_notnull_no_default"] = leads_nn
            details["tenants_notnull_no_default"] = tenants_nn

            # If core columns are missing, stop early
            core_ok = all(
                bool(checks.get(f"crm.leads.has_{c}", False))
                for c in ("id", "status", "payload", "created_at", "updated_at")
            )
            if not core_ok:
                conn.rollback()
                return {
                    "ok": False,
                    "service": "crm",
                    "db_contract": False,
                    "missing": [],
                    "checks": checks,
                    "details": details,
                    "elapsed_ms": int((time.time() - t0) * 1000),
                }

            # 4) Transactional INSERT into crm.leads
            inserted_lead_id: Optional[int] = None
            try:
                # Minimal insert: rely on defaults for status/payload/created_at/updated_at
                # We can optionally set company_name/contact_name if they exist (they do, but nullable).
                cur.execute(
                    """
                    INSERT INTO crm.leads (source, company_name, contact_name, email, phone, country, region)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id;
                    """,
                    ("smoke", "smoke-company", "smoke-contact", "smoke@example.local", "+10000000000", "RU", "RU-MOW"),
                )
                inserted_lead_id = int(cur.fetchone()[0])
                details["inserted_lead_id"] = inserted_lead_id

                # Touch update to validate UPDATE works
                cur.execute(
                    "UPDATE crm.leads SET company_name=%s WHERE id=%s;",
                    ("smoke-company-upd", inserted_lead_id),
                )
                details["updated_rows"] = int(cur.rowcount or 0)

                # 5) View queryability
                cur.execute("SELECT count(*) FROM crm.leads_trial_candidates_v;")
                details["trial_candidates_cnt"] = int(cur.fetchone()[0])

                conn.rollback()
                return {
                    "ok": True,
                    "service": "crm",
                    "db_contract": True,
                    "missing": [],
                    "checks": checks,
                    "details": details,
                    "elapsed_ms": int((time.time() - t0) * 1000),
                }

            except Exception as e:
                conn.rollback()
                details["insert_error"] = f"{type(e).__name__}: {e}"
                details["inserted_lead_id"] = inserted_lead_id
                return {
                    "ok": False,
                    "service": "crm",
                    "db_contract": True,  # objects exist, but DML path failed
                    "missing": [],
                    "checks": checks,
                    "details": details,
                    "elapsed_ms": int((time.time() - t0) * 1000),
                }
