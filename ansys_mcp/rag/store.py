"""Transactional local hybrid index. All readers see a single corpus generation."""

from collections import Counter
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
import hashlib
import io
import json
import os
import sqlite3
import uuid

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from threadpoolctl import threadpool_limits

from .documents import (
    QUERY_TERMS,
    ALIASES,
    Source,
    chunks,
    default_sources,
    files,
    metadata,
    pages,
    tokens,
)


@contextmanager
def connection(db, write=False):
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db, timeout=120)
    conn.row_factory = sqlite3.Row
    try:
        if write:
            conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield conn
        conn.commit()
    finally:
        conn.close()


def pack(matrix):

    buffer = io.BytesIO()
    np.savez_compressed(buffer, data=matrix)
    return buffer.getvalue()


def unpack(blob):

    with np.load(io.BytesIO(blob), allow_pickle=False) as data:
        return data["data"]


@lru_cache(maxsize=2)
def local_model(path, rerank=False):
    from sentence_transformers import CrossEncoder, SentenceTransformer

    cls = CrossEncoder if rerank else SentenceTransformer
    return cls(str(Path(path).resolve(strict=True)), local_files_only=True)


def embeddings(texts, raw):

    encoder = os.environ.get("ANSYS_RAG_EMBEDDING_MODEL")
    if encoder:
        vectors = local_model(encoder).encode(raw, normalize_embeddings=True)
        return {"encoder": str(Path(encoder).resolve())}, np.empty((0, 0)), vectors
    vectorizer = TfidfVectorizer(
        tokenizer=str.split, token_pattern=None, lowercase=False
    )
    sparse = vectorizer.fit_transform(texts)
    meta = {"vocab": vectorizer.vocabulary_, "idf": vectorizer.idf_.tolist()}
    if min(sparse.shape) < 2:
        return meta, np.empty((0, 0)), sparse.toarray()
    with threadpool_limits(limits=1):
        svd = TruncatedSVD(n_components=min(96, min(sparse.shape) - 1), random_state=42)
        vectors = svd.fit_transform(sparse)
    return meta, svd.components_.astype("float32"), vectors


def update(db, root, sources=None, replace_sources=False, only_if_missing=False):

    with connection(db, True) as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value BLOB)"
        )
        if (
            only_if_missing
            and c.execute(
                "SELECT name FROM pragma_table_info('chunks') WHERE name='software'"
            ).fetchone()
        ):
            return
        previous = c.execute("SELECT value FROM config WHERE key='sources'").fetchone()
        catalog = {} if replace_sources or not previous else json.loads(previous[0])
        for source in sources or []:
            path = str(Path(source.path).expanduser().resolve(strict=True))
            catalog[path] = {**source.model_dump(), "path": path}
        selected = {}
        for src in default_sources(root) + [
            Source(**spec) for spec in catalog.values()
        ]:
            for path in files(src):
                selected[path] = src
        c.execute("DROP TABLE IF EXISTS chunks")
        c.execute("DROP TABLE IF EXISTS terms")
        c.execute("""CREATE TABLE chunks(id INTEGER PRIMARY KEY, document TEXT, path TEXT,
                    module TEXT, version TEXT, kinds TEXT, page INTEGER, first INTEGER, last INTEGER, body TEXT, software TEXT, command_type TEXT)""")
        c.execute("CREATE INDEX document_idx ON chunks(document,id)")
        c.execute("CREATE VIRTUAL TABLE terms USING fts5(text)")
        texts, raw, skipped = [], [], []
        for path, src in selected.items():
            doc = hashlib.sha256(str(path).encode()).hexdigest()[:24]
            module, version, kinds, software, command_type = metadata(path, src)
            count = 0
            for page, body in pages(path):
                for first, last, excerpt in chunks(body):
                    terms = " ".join(
                        tokens(
                            path.stem
                            + " "
                            + module
                            + " "
                            + ALIASES.get(module, "")
                            + " "
                            + excerpt
                        )
                    )
                    rid = len(texts) + 1
                    texts.append(terms)
                    raw.append(excerpt)
                    c.execute(
                        "INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            rid,
                            doc,
                            str(path),
                            module,
                            version,
                            ",".join(kinds),
                            page,
                            first,
                            last,
                            excerpt,
                            software,
                            command_type,
                        ),
                    )
                    c.execute(
                        "INSERT INTO terms(rowid,text) VALUES (?,?)", (rid, terms)
                    )
                    count += 1
            if not count:
                skipped.append(str(path))
        if not texts:
            raise ValueError("No extractable text")
        meta, basis, vectors = embeddings(texts, raw)
        vectors = np.asarray(vectors, dtype="float32")
        vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
        generation = uuid.uuid4().hex
        config = {
            "vectors": pack(vectors),
            "basis": pack(basis),
            "model": json.dumps(meta),
            "sources": json.dumps(catalog),
            "generation": generation,
        }
        c.executemany("INSERT OR REPLACE INTO config VALUES (?,?)", config.items())
        return {
            "generation": generation,
            "documents": len(selected) - len(skipped),
            "chunks": len(texts),
            "empty_sources": skipped,
            "external_sources": list(catalog),
            "embedding": meta.get("encoder", "local-lsa"),
        }


def ensure(db, root):
    if db.exists():
        with connection(db) as c:
            if c.execute(
                "SELECT name FROM pragma_table_info('chunks') WHERE name='software'"
            ).fetchone():
                return
    update(db, root, only_if_missing=True)


def get_document(db, root, document_id, offset=0, limit=8):
    if offset < 0 or not 1 <= limit <= 50:
        raise ValueError("Use offset >= 0 and limit 1..50")
    ensure(db, root)
    with connection(db) as c:
        count = c.execute(
            "SELECT count(*) FROM chunks WHERE document=?", (document_id,)
        ).fetchone()[0]
        if not count:
            raise ValueError("Unknown document_id")
        rows = c.execute(
            "SELECT * FROM chunks WHERE document=? ORDER BY id LIMIT ? OFFSET ?",
            (document_id, limit, offset),
        )
        return {
            "document_id": document_id,
            "total_chunks": count,
            "offset": offset,
            "chunks": [citation(row) for row in rows],
        }


def citation(row):
    return {
        "document_id": row["document"],
        "path": row["path"],
        "module": row["module"],
        "version": row["version"],
        "software": row["software"],
        "command_type": row["command_type"],
        "kinds": row["kinds"].split(","),
        "page": row["page"] or None,
        "lines": [row["first"], row["last"]],
        "text": row["body"],
    }


def search(
    db,
    root,
    query,
    kind="",
    module="",
    version="",
    limit=5,
    software="",
    command_type="",
):

    expanded = (
        query
        + " "
        + " ".join(value for key, value in QUERY_TERMS.items() if key in query)
    )
    words = list(dict.fromkeys(tokens(expanded)))
    if not words or not 1 <= limit <= 30:
        raise ValueError("Supply a searchable query and limit 1..30")
    ensure(db, root)
    with connection(db) as c:
        conf = dict(c.execute("SELECT key,value FROM config"))
        meta = json.loads(conf["model"])
        parameters = (
            kind,
            kind,
            module,
            module,
            version,
            version,
            software,
            software,
            command_type,
            command_type,
        )
        rows = {
            r["id"]: r
            for r in c.execute(
                """SELECT * FROM chunks
            WHERE (?='' OR instr(','||kinds||',', ','||?||',')>0)
            AND (?='' OR module=?) AND (?='' OR version=?) AND (?='' OR software=? COLLATE NOCASE) AND (?='' OR command_type=? COLLATE NOCASE)""",
                parameters,
            )
        }
        if not rows:
            return {"generation": conf["generation"], "hits": []}
        expr = " OR ".join('"' + word + '"' for word in words[:100])
        lexical = [
            r[0]
            for r in c.execute(
                "SELECT rowid FROM terms WHERE terms MATCH ? ORDER BY rank", (expr,)
            )
            if r[0] in rows
        ]
        if "encoder" in meta:
            vec = local_model(meta["encoder"]).encode(
                [query], normalize_embeddings=True
            )[0]
        else:
            vocab = meta["vocab"]
            vec = np.zeros(len(vocab), dtype="float32")
            for word, n in Counter(tokens(expanded)).items():
                if word in vocab:
                    pos = vocab[word]
                    vec[pos] = n * meta["idf"][pos]
            basis = unpack(conf["basis"])
            if basis.size:
                vec = basis @ vec
        sims = unpack(conf["vectors"]) @ (vec / max(np.linalg.norm(vec), 1e-12))
        order = sorted(
            (i for i in rows if sims[i - 1] > 0.10), key=lambda i: -sims[i - 1]
        )
        scores = Counter()
        for weight, ranking in ((1.2, lexical), (1.0, order)):
            for rank, i in enumerate(ranking[: max(60, limit * 5)]):
                scores[i] += weight / (20 + rank)
        candidates = [i for i, v in scores.most_common(max(40, limit * 4))]
        reranker = os.environ.get("ANSYS_RAG_RERANK_MODEL")
        if candidates and reranker:
            values = local_model(reranker, True).predict(
                [(query, rows[i]["body"]) for i in candidates]
            )
            candidates = [i for _, i in sorted(zip(values, candidates), reverse=True)]
        else:
            for i in candidates:
                title_words = set(tokens(Path(rows[i]["path"]).stem))
                scores[i] += (
                    0.08
                    * len(title_words.intersection(words))
                    / max(1, len(title_words))
                )
                body = rows[i]["body"].casefold()
                scores[i] += (
                    0.035 * len(set(tokens(body)).intersection(words)) / len(words)
                )
                if query.casefold() in body:
                    scores[i] += 0.035
            candidates.sort(key=lambda i: -scores[i])
        hits = []
        for i in candidates:
            row = rows[i]
            if any(
                h["document_id"] == row["document"]
                and h["page"] == (row["page"] or None)
                and h["lines"][0] <= row["last"]
                and row["first"] <= h["lines"][1]
                for h in hits
            ):
                continue
            hits.append(
                {**citation(row), "vector_similarity": round(float(sims[i - 1]), 4)}
            )
            if len(hits) == limit:
                break
        return {"generation": conf["generation"], "hits": hits}
