"""Minimal Turso (libSQL) client over the HTTP pipeline protocol.

Pure stdlib — no native libsql dependency, so cold starts stay light and it
runs anywhere on Vercel's Python runtime (matches the zero-dependency codebase).
Talks to the Hrana-over-HTTP `/v2/pipeline` endpoint.

One pipeline call = one short-lived connection (statements run in order, then
close), so last_insert_rowid() only works when queried in the SAME batch() call
as its INSERT.
"""
import json
import urllib.request
import urllib.error


class TursoError(Exception):
    pass


class TursoClient:
    def __init__(self, url, token, timeout=25):
        if not url or not token:
            raise ValueError("Turso database URL and auth token are required")
        # Env value may be libsql://... — the HTTP endpoint is the https form.
        if url.startswith("libsql://"):
            url = "https://" + url[len("libsql://"):]
        self.endpoint = url.rstrip("/") + "/v2/pipeline"
        self.token = token
        self.timeout = timeout

    @staticmethod
    def _arg(v):
        if v is None:
            return {"type": "null", "value": None}
        if isinstance(v, bool):
            return {"type": "integer", "value": str(int(v))}
        if isinstance(v, int):
            return {"type": "integer", "value": str(v)}
        if isinstance(v, float):
            return {"type": "float", "value": v}
        if isinstance(v, (dict, list)):
            return {"type": "text", "value": json.dumps(v, ensure_ascii=False)}
        return {"type": "text", "value": str(v)}

    @staticmethod
    def _cell(cell):
        """Decode a Hrana typed value back to a Python scalar."""
        t = cell.get("type")
        v = cell.get("value")
        if t == "null":
            return None
        if t == "integer":
            return int(v)
        if t == "float":
            return float(v)
        return v  # text / blob (base64) returned as-is

    def batch(self, statements):
        """Run [(sql, args), ...] in one pipeline. Returns a list of result dicts
        {"columns": [...], "rows": [[scalar, ...], ...]}, one per statement."""
        requests = [
            {"type": "execute",
             "stmt": {"sql": sql, "args": [self._arg(a) for a in (args or [])]}}
            for sql, args in statements
        ]
        requests.append({"type": "close"})
        payload = json.dumps({"requests": requests}).encode()
        req = urllib.request.Request(self.endpoint, data=payload, headers={
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise TursoError(f"HTTP {e.code}: {e.read().decode(errors='replace')}")

        out = []
        for r in body.get("results", []):
            if r.get("type") == "error":
                raise TursoError((r.get("error") or {}).get("message", "unknown error"))
            resp_obj = r.get("response") or {}
            if resp_obj.get("type") != "execute":
                continue
            result = resp_obj.get("result") or {}
            cols = [c.get("name") for c in result.get("cols", [])]
            rows = [[self._cell(c) for c in row] for row in result.get("rows", [])]
            out.append({"columns": cols, "rows": rows})
        return out

    def execute(self, sql, args=None):
        """Single-statement convenience wrapper."""
        return self.batch([(sql, args or [])])[0]

    def executemany(self, sql, rows, chunk=50):
        """Run the same SQL for many arg-tuples, chunked into pipeline batches.
        Returns the number of statements executed."""
        total = 0
        for i in range(0, len(rows), chunk):
            self.batch([(sql, args) for args in rows[i:i + chunk]])
            total += len(rows[i:i + chunk])
        return total
