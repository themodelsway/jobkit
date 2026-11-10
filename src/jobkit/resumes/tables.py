"""Resume data and curation in the database (see `jobkit.store.split` for the approach).

Companies with their roles and bullets, the skills, the resume's own sections, the scan ledger and the
unparsed report are stored as rows; curation (the user's certifications, skill rules, bullet themes, ...)
is one row per entry. Functions take and return the same dicts the tools used to keep in JSON files.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any

from jobkit import store

Record = dict[str, Any]
COMPANY_PARTS = ("roles", "bullets")


# ---------------------------------------------------------------- companies

def has_resume_data() -> bool:
    """True once a build has stored the skills (the marker that resume data exists)."""
    with store.transaction(write=False) as conn:
        return conn.execute("SELECT 1 FROM meta WHERE key='resume.skills'").fetchone() is not None


def load_companies() -> dict[str, Record]:
    """{company id: company with roles and bullets}, in stored order."""
    out: dict[str, Record] = {}
    with store.transaction(write=False) as conn:
        for company in store.records(conn, "SELECT id, body FROM company ORDER BY position", (), ("id",)):
            cid = company["id"]
            company["roles"] = store.bodies(conn, "SELECT body FROM role WHERE company_id=? ORDER BY position", (cid,))
            company["bullets"] = store.records(
                conn, "SELECT id, body FROM bullet WHERE company_id=? ORDER BY position", (cid,), ("id",))
            out[cid] = company
    return out


def replace_companies(companies: Mapping[str, Mapping[str, Any]]) -> None:
    """Store every company; companies not in `companies` are removed with their roles and bullets."""
    with store.transaction() as conn:
        for position, (cid, company) in enumerate(companies.items()):
            _, body = store.split({k: v for k, v in company.items() if k not in COMPANY_PARTS}, ("id",))
            conn.execute("INSERT INTO company(id, position, body) VALUES(?,?,?) "
                         "ON CONFLICT(id) DO UPDATE SET position=excluded.position, body=excluded.body",
                         (cid, position, body))
            _save_parts(conn, cid, company)
        store.keep_only(conn, "company", "id", list(companies))


def _save_parts(conn: Any, cid: str, company: Mapping[str, Any]) -> None:
    """Replace the roles and bullets of one company."""
    conn.execute("DELETE FROM role WHERE company_id=?", (cid,))
    conn.execute("DELETE FROM bullet WHERE company_id=?", (cid,))
    conn.executemany("INSERT INTO role(company_id, position, body) VALUES(?,?,?)",
                     [(cid, i, store.dump(r)) for i, r in enumerate(company.get("roles", []))])
    for position, bullet in enumerate(company.get("bullets", [])):
        (bullet_id,), body = store.split(bullet, ("id",))
        conn.execute("INSERT INTO bullet(company_id, id, position, body) VALUES(?,?,?,?)", (cid, bullet_id, position, body))


# ---------------------------------------------------------------- skills, sections, index, ledger

def load_skills() -> Record | None:
    """The skills document ({groups: {name: [skill]}, ...}), or None before the first build."""
    with store.transaction(write=False) as conn:
        head = store.meta_get(conn, "resume.skills", None)
        if head is None:
            return None
        rest, order = head["rest"], head["groups"]
        groups: Record = {name: [] for name in order}
        for row in conn.execute("SELECT group_name, body FROM skill ORDER BY group_name, position"):
            groups[row["group_name"]].append(json.loads(row["body"]))
    return {"groups": groups, **rest}


def replace_skills(skills: Mapping[str, Any]) -> None:
    """Store the skills document."""
    groups = skills.get("groups", {})
    rest = {k: v for k, v in skills.items() if k != "groups"}
    with store.transaction() as conn:
        store.meta_put(conn, "resume.skills", {"groups": list(groups), "rest": rest})
        conn.execute("DELETE FROM skill")
        conn.executemany("INSERT INTO skill(group_name, position, body) VALUES(?,?,?)",
                         [(g, i, store.dump(s)) for g, items in groups.items() for i, s in enumerate(items)])


def load_profile() -> Record | None:
    """The resume's own sections ({summaries: [...], education: [...], ...}), or None before the first build."""
    with store.transaction(write=False) as conn:
        sections = store.meta_get(conn, "resume.profile", None)
        if sections is None:
            return None
        out: Record = {name: [] for name in sections}
        for row in conn.execute("SELECT section, body FROM resume_item ORDER BY section, position"):
            out[row["section"]].append(json.loads(row["body"]))
    return out


def replace_profile(profile: Mapping[str, Sequence[Any]]) -> None:
    """Store the resume's own sections."""
    with store.transaction() as conn:
        store.meta_put(conn, "resume.profile", list(profile))
        conn.execute("DELETE FROM resume_item")
        conn.executemany("INSERT INTO resume_item(section, position, body) VALUES(?,?,?)",
                         [(name, i, store.dump(item)) for name, items in profile.items() for i, item in enumerate(items)])


def load_index() -> Record | None:
    """The generated overview (companies, skill counts, themes), or None."""
    with store.transaction(write=False) as conn:
        return store.meta_get(conn, "resume.index", None)


def save_index(index: Mapping[str, Any]) -> None:
    """Store the generated overview."""
    with store.transaction() as conn:
        store.meta_put(conn, "resume.index", index)


def load_ledger() -> dict[str, Record]:
    """{resume file: what was read of it (kind, mtime, size, sha256, processed_at)}."""
    with store.transaction(write=False) as conn:
        return {r["file"]: json.loads(r["body"]) for r in conn.execute("SELECT file, body FROM ledger ORDER BY file")}


def replace_ledger(ledger: Mapping[str, Mapping[str, Any]]) -> None:
    """Store the scan ledger."""
    with store.transaction() as conn:
        conn.execute("DELETE FROM ledger")
        conn.executemany("INSERT INTO ledger(file, body) VALUES(?,?)", [(f, store.dump(e)) for f, e in ledger.items()])


def load_unparsed() -> dict[str, Any]:
    """{resume file: why it could not be read}."""
    with store.transaction(write=False) as conn:
        return {r["file"]: json.loads(r["body"]) for r in conn.execute("SELECT file, body FROM unparsed ORDER BY file")}


def replace_unparsed(unparsed: Mapping[str, Any]) -> None:
    """Store the unparsed report."""
    with store.transaction() as conn:
        conn.execute("DELETE FROM unparsed")
        conn.executemany("INSERT INTO unparsed(file, body) VALUES(?,?)", [(f, store.dump(e)) for f, e in unparsed.items()])


# ---------------------------------------------------------------- curation

CURATION_FILES = ("curated", "themes")


def kind_key(value: Any) -> str:
    """The row key of a list entry: the entry itself as canonical JSON."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def has_curation(file: str) -> bool:
    """True once the curation file has been stored (even if empty)."""
    with store.transaction(write=False) as conn:
        return conn.execute("SELECT 1 FROM meta WHERE key=?", (f"curation.{file}",)).fetchone() is not None


def load_curation(file: str) -> Record | None:
    """One curation file as a dict ({kind: list or dict}), or None when it was never stored."""
    with store.transaction(write=False) as conn:
        shape = store.meta_get(conn, f"curation.{file}", None)
        if shape is None:
            return None
        out: Record = {kind: ([] if how == "list" else {}) for kind, how in shape.items()}
        for row in conn.execute("SELECT kind, key, body FROM curation WHERE file=? ORDER BY kind, position", (file,)):
            how = shape[row["kind"]]
            value = json.loads(row["body"])
            if how == "list":
                out[row["kind"]].append(value)
            elif how == "dict":
                out[row["kind"]][row["key"]] = value
            else:
                out[row["kind"]] = value
    return out


def save_curation(file: str, data: Mapping[str, Any]) -> None:
    """Store one curation file, one row per entry."""
    shape = {kind: ("list" if isinstance(v, list) else "dict" if isinstance(v, dict) else "value")
             for kind, v in data.items()}
    with store.transaction() as conn:
        store.meta_put(conn, f"curation.{file}", shape)
        conn.execute("DELETE FROM curation WHERE file=?", (file,))
        rows: list[tuple[str, str, str, int, str]] = []
        for kind, value in data.items():
            if isinstance(value, list):
                rows += [(file, kind, kind_key(v), i, store.dump(v)) for i, v in enumerate(value)]
            elif isinstance(value, dict):
                rows += [(file, kind, k, i, store.dump(v)) for i, (k, v) in enumerate(value.items())]
            else:
                rows.append((file, kind, "", 0, store.dump(value)))
        conn.executemany("INSERT OR REPLACE INTO curation(file, kind, key, position, body) VALUES(?,?,?,?,?)", rows)


def curation_digest() -> str:
    """A fingerprint of the whole curation (both files), to tell whether it changed since the last build."""
    texts = [store.dump(load_curation(file)) for file in CURATION_FILES]
    return sha256("\n".join(texts).encode("utf-8")).hexdigest()


def load_built_curation() -> str | None:
    """The curation fingerprint the stored resume data was built with, or None."""
    with store.transaction(write=False) as conn:
        return store.meta_get(conn, "resume.curation_digest", None)


def save_built_curation(digest: str) -> None:
    """Remember which curation the stored resume data was built with."""
    with store.transaction() as conn:
        store.meta_put(conn, "resume.curation_digest", digest)


def stored_texts() -> dict[str, str]:
    """{label: JSON text} for everything stored about the resumes (for the contact-details check and snapshots)."""
    out = {f"company {cid}": store.dump(company) for cid, company in load_companies().items()}
    for label, value in (("skills", load_skills()), ("profile", load_profile()), ("index", load_index()),
                         ("ledger", load_ledger()), ("unparsed", load_unparsed()),
                         ("curated", load_curation("curated")), ("curation themes", load_curation("themes"))):
        if value is not None:
            out[label] = store.dump(value)
    return out
