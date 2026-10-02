import sqlite3
import json
import os
import datetime

DB_PATH = os.environ.get("DATABASE_PATH") or os.path.join(os.path.dirname(__file__), "data.sqlite3")

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    country TEXT NOT NULL,
    contact_email TEXT,
    contact_phone TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    client_name TEXT NOT NULL,
    country TEXT NOT NULL,
    exchange_rate REAL NOT NULL,
    is_items_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    FOREIGN KEY (client_id) REFERENCES clients(id)
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    findings_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def now():
    return datetime.datetime.utcnow().isoformat()


# --- Clients ---

def create_client(name, country, email="", phone="", notes=""):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO clients (name, country, contact_email, contact_phone, notes, created_at) VALUES (?,?,?,?,?,?)",
        (name, country, email, phone, notes, now()),
    )
    conn.commit()
    client_id = cur.lastrowid
    conn.close()
    return client_id


def get_or_create_client(name, country):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM clients WHERE lower(name) = lower(?)", (name,)
    ).fetchone()
    if row:
        conn.close()
        return row["id"]
    conn.close()
    return create_client(name, country)


def list_clients():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM clients ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_client(client_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# --- Quotations ---

def save_quotation(client_id, client_name, country, exchange_rate, is_items, result, status="draft"):
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO quotations
           (client_id, client_name, country, exchange_rate, is_items_json, result_json, status, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (client_id, client_name, country, exchange_rate,
         json.dumps(is_items), json.dumps(result), status, now()),
    )
    conn.commit()
    qid = cur.lastrowid
    conn.close()
    return qid


def list_quotations():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM quotations ORDER BY created_at DESC").fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["is_items"] = json.loads(d.pop("is_items_json"))
        d["result"] = json.loads(d.pop("result_json"))
        out.append(d)
    return out


def get_quotation(qid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM quotations WHERE id = ?", (qid,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["is_items"] = json.loads(d.pop("is_items_json"))
    d["result"] = json.loads(d.pop("result_json"))
    return d


def update_quotation_status(qid, status):
    conn = get_conn()
    conn.execute("UPDATE quotations SET status = ? WHERE id = ?", (status, qid))
    conn.commit()
    conn.close()


# --- Reviews ---

def save_review(filename, findings):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO reviews (filename, findings_json, created_at) VALUES (?,?,?)",
        (filename, json.dumps(findings), now()),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def list_reviews():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM reviews ORDER BY created_at DESC").fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["findings"] = json.loads(d.pop("findings_json"))
        out.append(d)
    return out
