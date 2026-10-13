"""The catalogue preserves evidence; review is a separate human decision."""
import hashlib
import json
import os
import random
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = Path(os.environ.get('CATFACTS_DB', ROOT / 'data/catalog.sqlite3'))

@contextmanager
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    try:
        with db:
            yield db
    finally:
        db.close()

def initialize():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS facts (
          id TEXT PRIMARY KEY, text TEXT NOT NULL, category TEXT NOT NULL,
          source TEXT NOT NULL, source_title TEXT NOT NULL, revision TEXT,
          image TEXT, image_credit TEXT, status TEXT NOT NULL DEFAULT 'candidate');
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, payload TEXT NOT NULL, attempts INTEGER DEFAULT 0,
          due REAL DEFAULT 0, status TEXT DEFAULT 'pending', error TEXT);
        ''')
        for fact in json.loads((ROOT / 'data/seed.json').read_text()):
            insert(db, fact)
            db.execute('UPDATE facts SET image=?,image_credit=? WHERE source=? AND text=?',
                       (fact.get('image'),fact.get('image_credit'),fact['source'],fact['text']))

def insert(db, fact):
    fact = dict(fact)
    fact.setdefault('id', hashlib.sha256((fact['source'] + fact['text']).encode()).hexdigest()[:20])
    fields = ['id','text','category','source','source_title','revision','image','image_credit','status']
    db.execute('INSERT OR IGNORE INTO facts VALUES (?,?,?,?,?,?,?,?,?)',
               [fact.get(key, 'candidate' if key == 'status' else None) for key in fields])

def catalogue(query='', category=''):
    with connect() as db:
        return [dict(row) for row in db.execute(
            "SELECT * FROM facts WHERE status='approved' AND text LIKE ? AND (?='' OR category=?) ORDER BY category,id",
            ('%' + query[:200] + '%', category, category))]

def random_fact(category=''):
    facts = catalogue(category=category)
    return random.SystemRandom().choice(facts) if facts else None

def stats():
    with connect() as db:
        counts = dict(db.execute('SELECT status,count(*) FROM facts GROUP BY status'))
        categories = [r[0] for r in db.execute("SELECT DISTINCT category FROM facts WHERE status='approved' ORDER BY category")]
        jobs = dict(db.execute('SELECT status,count(*) FROM jobs GROUP BY status'))
    return dict(approved=counts.get('approved',0), candidates=counts.get('candidate',0), categories=categories, jobs=jobs)
