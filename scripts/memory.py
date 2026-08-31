#!/usr/bin/env python3
"""
Persistent memory for the local research agent.

Two stores, deliberately:
  * SQLite  - the authoritative record. Sessions, their sources and their
              extracted findings. Cheap, exact, greppable, survives anything.
  * Chroma  - semantic recall only. Lets "have I looked at X before?" work when
              the wording differs from last time. Rebuildable from SQLite, so
              it is a cache, not a source of truth.

Embeddings come from nomic-embed-text-v1.5 via Ollama: 768-dim, mean pooled,
**2048-token context**. That context is the reason for CHUNK_CHARS below - a
longer chunk is silently truncated by the embedder, which quietly degrades
recall rather than erroring.

Usage:
    ./memory.py recall "wan 2.2 vram"     # semantic search over past research
    ./memory.py recent 10                 # most recent sessions
    ./memory.py stats                     # counts + disk
    ./memory.py reindex                   # rebuild Chroma from SQLite
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_lib as R

ROOT = Path(os.environ.get("RESEARCH_HOME", Path.home() / "AI" / "research"))
DB_PATH = ROOT / "research.db"
CHROMA_PATH = Path.home() / "AI" / "models" / "chroma"
COLLECTION = "research"

# nomic-embed-text-v1.5 truncates past 2048 tokens. ~4 chars/token is the usual
# English rule of thumb, so 6000 chars (~1500 tok) leaves comfortable headroom.
CHUNK_CHARS = 6000
CHUNK_OVERLAP = 400

DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,
    question    TEXT    NOT NULL,
    model       TEXT    NOT NULL,
    rounds      INTEGER NOT NULL DEFAULT 0,
    elapsed_s   REAL    NOT NULL DEFAULT 0,
    status      TEXT    NOT NULL DEFAULT 'ok',
    report_path TEXT,
    report      TEXT
);
CREATE TABLE IF NOT EXISTS sources (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    url        TEXT    NOT NULL,
    title      TEXT,
    backend    TEXT,
    fetched    INTEGER NOT NULL DEFAULT 0,
    note       TEXT
);
CREATE TABLE IF NOT EXISTS findings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    url        TEXT,
    claim      TEXT NOT NULL,
    quote      TEXT
);
CREATE INDEX IF NOT EXISTS idx_sources_session  ON sources(session_id);
CREATE INDEX IF NOT EXISTS idx_findings_session ON findings(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at);
"""


def connect() -> sqlite3.Connection:
    ROOT.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(DDL)
    return con


# ---------------------------------------------------------------- chroma ----

def _collection():
    """None if chromadb is unavailable - memory must still work without it.

    embedding_function=None is NOT optional: get_or_create_collection otherwise
    installs Chroma's default ONNX MiniLM (384-dim) on a collection we only ever
    feed 768-dim nomic vectors. It stays dormant while we pass embeddings
    explicitly, then blows up the moment anything queries by text.
    """
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        return client.get_or_create_collection(
            COLLECTION,
            embedding_function=None,
            metadata={"embed_model": "nomic-embed-text", "dim": 768})
    except Exception as e:
        print(f"  [chroma unavailable: {type(e).__name__}: {e}]", file=sys.stderr)
        return None


def _chunks(text: str) -> list[str]:
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + CHUNK_CHARS])
        i += CHUNK_CHARS - CHUNK_OVERLAP
    return out or [""]


def index_session(session_id: int, question: str, report: str) -> int:
    """Embed a session for semantic recall. Returns chunks indexed."""
    col = _collection()
    if col is None:
        return 0
    # The question carries most of the recall signal, so it prefixes every
    # chunk - otherwise a chunk from deep in a report has no topical anchor.
    n = 0
    for j, ch in enumerate(_chunks(report)):
        vec = R.embed(f"{question}\n\n{ch}")
        if vec is None:
            continue
        col.upsert(ids=[f"s{session_id}-c{j}"], embeddings=[vec],
                   documents=[ch[:2000]],
                   metadatas=[{"session_id": session_id, "question": question,
                               "chunk": j}])
        n += 1
    return n


def recall(query: str, k: int = 5) -> list[dict]:
    """Semantically similar past sessions, deduped to one hit per session."""
    col = _collection()
    if col is None:
        return []
    vec = R.embed(query)
    if vec is None:
        return []
    try:
        res = col.query(query_embeddings=[vec], n_results=k * 3)
    except Exception:
        return []
    seen, out = set(), []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0],
                               res["distances"][0]):
        sid = meta.get("session_id")
        if sid in seen:
            continue
        seen.add(sid)
        out.append({"session_id": sid, "question": meta.get("question", ""),
                    "excerpt": doc[:400], "distance": round(dist, 2)})
        if len(out) >= k:
            break
    return out


# ----------------------------------------------------------------- write ----

def save_session(question, report, sources, findings, model, rounds,
                 elapsed_s, status="ok", report_path=None) -> int:
    con = connect()
    cur = con.execute(
        "INSERT INTO sessions (created_at,question,model,rounds,elapsed_s,"
        "status,report_path,report) VALUES (?,?,?,?,?,?,?,?)",
        (time.strftime("%Y-%m-%dT%H:%M:%S"), question, model, rounds,
         round(elapsed_s, 1), status, str(report_path or ""), report))
    sid = cur.lastrowid
    con.executemany(
        "INSERT INTO sources (session_id,url,title,backend,fetched,note) "
        "VALUES (?,?,?,?,?,?)",
        [(sid, s.get("url", ""), s.get("title", ""), s.get("source", ""),
          int(s.get("fetched", 0)), s.get("error", "")) for s in sources])
    con.executemany(
        "INSERT INTO findings (session_id,url,claim,quote) VALUES (?,?,?,?)",
        [(sid, f.get("url", ""), f.get("claim", ""), f.get("quote", ""))
         for f in findings])
    con.commit()
    con.close()
    return sid


# ------------------------------------------------------------------ read ----

def recent(n: int = 10) -> list[sqlite3.Row]:
    con = connect()
    rows = con.execute(
        "SELECT id,created_at,question,rounds,elapsed_s,status,report_path "
        "FROM sessions ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    con.close()
    return rows


def stats() -> dict:
    con = connect()
    g = lambda q: con.execute(q).fetchone()[0]
    d = {"sessions": g("SELECT COUNT(*) FROM sessions"),
         "sources": g("SELECT COUNT(*) FROM sources"),
         "findings": g("SELECT COUNT(*) FROM findings"),
         "db_kb": DB_PATH.stat().st_size // 1024 if DB_PATH.exists() else 0}
    con.close()
    col = _collection()
    d["vectors"] = col.count() if col is not None else "n/a"
    return d


def reindex() -> int:
    """Rebuild Chroma from SQLite. Chroma is a cache; this is always safe."""
    con = connect()
    rows = con.execute("SELECT id,question,report FROM sessions").fetchall()
    con.close()
    total = 0
    for r in rows:
        total += index_session(r["id"], r["question"], r["report"] or "")
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("recall"); p.add_argument("query"); p.add_argument("-k", type=int, default=5)
    p = sub.add_parser("recent"); p.add_argument("n", type=int, nargs="?", default=10)
    sub.add_parser("stats")
    sub.add_parser("reindex")
    a = ap.parse_args()

    if a.cmd == "recall":
        hits = recall(a.query, a.k)
        if not hits:
            print("  no matching past research")
        for h in hits:
            print(f"  [{h['distance']}] session {h['session_id']}: {h['question']}")
            print(f"        {h['excerpt'][:150].strip()}...")
    elif a.cmd == "recent":
        for r in recent(a.n):
            print(f"  {r['id']:4}  {r['created_at']}  {r['status']:6}  "
                  f"{r['rounds']}r {r['elapsed_s']:6.0f}s  {r['question'][:70]}")
    elif a.cmd == "stats":
        for k, v in stats().items():
            print(f"  {k:10} {v}")
    elif a.cmd == "reindex":
        print(f"  indexed {reindex()} chunks")


if __name__ == "__main__":
    main()
