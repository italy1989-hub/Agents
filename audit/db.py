import os
import sqlite3

DB_PATH = os.getenv("AUDIT_DB", "audit.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY, title TEXT, manager_id INTEGER, date_create TEXT,
    date_modify TEXT, emails TEXT, phones TEXT, return_date TEXT);
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY, name TEXT, post TEXT, company_id INTEGER,
    manager_id INTEGER, emails TEXT);
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY, title TEXT, company_id INTEGER, contact_id INTEGER,
    manager_id INTEGER, stage_id TEXT, stage_semantic TEXT, closed TEXT,
    category_id INTEGER, date_create TEXT, date_modify TEXT);
CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY, owner_type_id INTEGER, owner_id INTEGER, company_id INTEGER,
    type_id INTEGER, provider_id TEXT, direction INTEGER, completed TEXT,
    created TEXT, deadline TEXT, subject TEXT);
CREATE TABLE IF NOT EXISTS ownership (
    company_id INTEGER, manager_id INTEGER, since TEXT, PRIMARY KEY (company_id, since));
CREATE INDEX IF NOT EXISTS ix_act_company ON activities(company_id);
CREATE INDEX IF NOT EXISTS ix_deal_company ON deals(company_id);
CREATE INDEX IF NOT EXISTS ix_contact_company ON contacts(company_id);
"""


def connect(path: str | None = None) -> sqlite3.Connection:
    db = sqlite3.connect(path or DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db
