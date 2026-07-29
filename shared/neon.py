"""Minimal Neon/Postgres client for Kani Sensei.

Uses psycopg with server-side prepared statements disabled. That matters for
Neon's pooled connection strings, which sit behind PgBouncer.
"""

import psycopg


class NeonClient:
    def __init__(self, database_url, timeout=25):
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        self.database_url = database_url
        self.timeout = timeout

    def connect(self):
        return psycopg.connect(
            self.database_url,
            connect_timeout=self.timeout,
            prepare_threshold=None,
        )

    def execute(self, sql, args=None, fetch=False):
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, args or [])
                rows = cur.fetchall() if fetch else []
            conn.commit()
        return rows

    def executemany(self, sql, rows, chunk=100):
        total = 0
        with self.connect() as conn:
            with conn.cursor() as cur:
                for i in range(0, len(rows), chunk):
                    batch = rows[i:i + chunk]
                    cur.executemany(sql, batch)
                    total += len(batch)
            conn.commit()
        return total
