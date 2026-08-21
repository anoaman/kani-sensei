"""Minimal Neon/Postgres client for Kani Sensei.

Uses psycopg with server-side prepared statements disabled. That matters for
Neon's pooled connection strings, which sit behind PgBouncer.

By default every execute() opens and closes a connection. That is brutally
slow on Vercel (TLS + pooler handshake per query). Callers that run several
statements should wrap them in reuse() so they share one connection.
"""

from contextlib import contextmanager

import psycopg


class NeonClient:
    def __init__(self, database_url, timeout=25):
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        self.database_url = database_url
        self.timeout = timeout
        self._reuse = None

    def connect(self):
        return psycopg.connect(
            self.database_url,
            connect_timeout=self.timeout,
            prepare_threshold=None,
        )

    @contextmanager
    def reuse(self):
        """Keep one connection open for nested execute() / executemany() calls."""
        if self._reuse is not None:
            yield self._reuse
            return
        with self.connect() as conn:
            self._reuse = conn
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                self._reuse = None

    def _run(self, conn, sql, args, fetch):
        with conn.cursor() as cur:
            cur.execute(sql, args or [])
            return cur.fetchall() if fetch else []

    def execute(self, sql, args=None, fetch=False):
        if self._reuse is not None:
            # One commit at the end of reuse() — not after every statement.
            return self._run(self._reuse, sql, args, fetch)
        with self.connect() as conn:
            rows = self._run(conn, sql, args, fetch)
            conn.commit()
            return rows

    def executemany(self, sql, rows, chunk=100):
        def _write(conn):
            total = 0
            with conn.cursor() as cur:
                for i in range(0, len(rows), chunk):
                    batch = rows[i:i + chunk]
                    cur.executemany(sql, batch)
                    total += len(batch)
            return total

        if self._reuse is not None:
            return _write(self._reuse)
        with self.connect() as conn:
            total = _write(conn)
            conn.commit()
            return total

    def has_relation(self, name):
        """True if a table/view exists. Does not error (or abort a txn) if missing."""
        rows = self.execute("select to_regclass(%s)", [name], fetch=True)
        return bool(rows and rows[0][0])
