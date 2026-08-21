"""
Tiny SQLite-backed store for the Shelf Protocol Registry.
Keeps the whole shelf.json record as JSON, with a few indexed columns for search.
Swap this for Postgres when you outgrow it — the interface stays the same.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Optional

DB_PATH = os.environ.get("SHELF_DB", os.path.join(os.path.dirname(__file__), "shelf.sqlite"))


class DB:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS merchants (
                    domain     TEXT PRIMARY KEY,
                    name       TEXT,
                    categories TEXT,
                    protocol   TEXT,
                    verified   INTEGER DEFAULT 0,
                    max_order  REAL DEFAULT 0,
                    blob       TEXT
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS products (
                    domain      TEXT,
                    sku         TEXT,
                    name        TEXT,
                    description TEXT,
                    categories  TEXT,
                    price_usd   REAL,
                    url         TEXT,
                    in_stock    INTEGER,
                    PRIMARY KEY (domain, sku)
                )
                """
            )
            self._conn.commit()

    def _upsert_unlocked(self, domain: str, record: dict):
        """Write record to DB. Caller must hold self._lock."""
        m = record.get("merchant", {})
        self._conn.execute(
            """
            INSERT INTO merchants (domain, name, categories, protocol, verified, max_order, blob)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(domain) DO UPDATE SET
                name=excluded.name,
                categories=excluded.categories,
                protocol=excluded.protocol,
                verified=excluded.verified,
                max_order=excluded.max_order,
                blob=excluded.blob
            """,
            (
                domain,
                m.get("name", ""),
                " ".join(m.get("categories", [])),
                record.get("checkout", {}).get("protocol", "manual"),
                1 if record.get("trust", {}).get("verified_domain") else 0,
                record.get("agent_policy", {}).get("max_autonomous_order_usd", 0) or 0,
                json.dumps(record),
            ),
        )
        self._conn.commit()

    def upsert(self, domain: str, record: dict):
        with self._lock:
            self._upsert_unlocked(domain, record)

    def get(self, domain: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT blob FROM merchants WHERE domain = ?", (domain,)
            ).fetchone()
        return json.loads(row["blob"]) if row else None

    def bump_lookup(self, domain: str):
        with self._lock:
            row = self._conn.execute(
                "SELECT blob FROM merchants WHERE domain = ?", (domain,)
            ).fetchone()
            if not row:
                return
            record = json.loads(row["blob"])
            record.setdefault("_meta", {})
            record["_meta"]["lookups"] = record["_meta"].get("lookups", 0) + 1
            self._upsert_unlocked(domain, record)

    def transform(self, domain: str, fn) -> Optional[dict]:
        """Atomic read-modify-write: apply fn to the freshest record under one
        lock and persist the result. Returns the new record, or None if the
        domain is unknown. Use this instead of get()+upsert() whenever the
        mutation must not clobber concurrent writes."""
        with self._lock:
            row = self._conn.execute(
                "SELECT blob FROM merchants WHERE domain = ?", (domain,)
            ).fetchone()
            if not row:
                return None
            record = fn(json.loads(row["blob"]))
            self._upsert_unlocked(domain, record)
            return record

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) AS c FROM merchants").fetchone()["c"]

    def search(self, q=None, category=None, protocol=None, verified=None,
               max_order_usd=None, limit=20) -> list[dict]:
        clauses, params = [], []
        if q:
            clauses.append("(LOWER(name) LIKE ? OR LOWER(categories) LIKE ? OR LOWER(blob) LIKE ?)")
            like = f"%{q.lower()}%"
            params += [like, like, like]
        if category:
            clauses.append("LOWER(categories) LIKE ?")
            params.append(f"%{category.lower()}%")
        if protocol:
            clauses.append("LOWER(protocol) = ?")
            params.append(protocol.lower())
        if verified is True:
            clauses.append("verified = 1")
        if max_order_usd is not None:
            clauses.append("max_order >= ?")
            params.append(max_order_usd)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT blob FROM merchants {where} ORDER BY verified DESC, max_order DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [json.loads(r["blob"]) for r in rows]

    def set_catalog(self, domain: str, items: list[dict]):
        """Replace a merchant's cached catalog with freshly validated items."""
        rows = [
            (domain, it["sku"], it["name"], it["description"],
             " ".join(it["categories"]), it["price_usd"], it["url"],
             1 if it["in_stock"] else 0)
            for it in items
        ]
        with self._lock:
            self._conn.execute("DELETE FROM products WHERE domain = ?", (domain,))
            self._conn.executemany(
                "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows
            )
            self._conn.commit()

    @staticmethod
    def _product_row(r) -> dict:
        return {
            "domain": r["domain"], "sku": r["sku"], "name": r["name"],
            "description": r["description"],
            "categories": r["categories"].split() if r["categories"] else [],
            "price_usd": r["price_usd"], "url": r["url"],
            "in_stock": bool(r["in_stock"]),
        }

    def get_catalog(self, domain: str, q=None, limit=100) -> list[dict]:
        clauses, params = ["domain = ?"], [domain]
        if q:
            clauses.append("(LOWER(name) LIKE ? OR LOWER(description) LIKE ? OR LOWER(categories) LIKE ?)")
            like = f"%{q.lower()}%"
            params += [like, like, like]
        params.append(limit)
        sql = f"SELECT * FROM products WHERE {' AND '.join(clauses)} ORDER BY sku LIMIT ?"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._product_row(r) for r in rows]

    def search_products(self, q=None, category=None, verified=None,
                        in_stock=None, limit=20) -> list[dict]:
        clauses, params = [], []
        if q:
            clauses.append("(LOWER(p.name) LIKE ? OR LOWER(p.description) LIKE ? OR LOWER(p.categories) LIKE ?)")
            like = f"%{q.lower()}%"
            params += [like, like, like]
        if category:
            clauses.append("LOWER(p.categories) LIKE ?")
            params.append(f"%{category.lower()}%")
        if verified is True:
            clauses.append("m.verified = 1")
        if in_stock is True:
            clauses.append("p.in_stock = 1")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            "SELECT p.*, m.name AS merchant_name, m.verified AS merchant_verified "
            f"FROM products p JOIN merchants m ON p.domain = m.domain {where} "
            "ORDER BY m.verified DESC, p.price_usd ASC LIMIT ?"
        )
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [
            {**self._product_row(r),
             "merchant_name": r["merchant_name"],
             "merchant_verified": bool(r["merchant_verified"])}
            for r in rows
        ]

    def stats(self) -> dict:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) AS c FROM merchants").fetchone()["c"]
            verified = self._conn.execute("SELECT COUNT(*) AS c FROM merchants WHERE verified=1").fetchone()["c"]
            products = self._conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
            rows = self._conn.execute("SELECT blob FROM merchants").fetchall()
        lookups = sum(json.loads(r["blob"]).get("_meta", {}).get("lookups", 0) for r in rows)
        return {
            "merchants_indexed": total,
            "verified_merchants": verified,
            "products_indexed": products,
            "total_agent_lookups": lookups,
        }
