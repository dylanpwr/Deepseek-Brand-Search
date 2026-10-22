import sqlite3, json
from datetime import datetime, timezone
from pathlib import Path

def now():
    return datetime.now(timezone.utc).isoformat()

class Store:
    def __init__(self, path='data/audits.sqlite'):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db=sqlite3.connect(path, timeout=30)
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, started TEXT, finished TEXT,
          fingerprint TEXT, manifest TEXT, status TEXT);
        CREATE TABLE IF NOT EXISTS searches(run_id INTEGER, query_id TEXT, query TEXT, category TEXT,
          branded INTEGER, language TEXT, priority INTEGER, purchase_intent REAL, canada_relevance REAL,
          status TEXT, error TEXT, observed_at TEXT, cache_hit INTEGER, raw TEXT,
          PRIMARY KEY(run_id,query_id));
        CREATE TABLE IF NOT EXISTS results(run_id INTEGER, query_id TEXT, rank INTEGER,
          title TEXT, url TEXT, domain TEXT, snippet TEXT, summary TEXT, rerank_score REAL,
          authority_tier TEXT, publication_date TEXT, brands TEXT, official_brand TEXT,
          classification TEXT, PRIMARY KEY(run_id,query_id,rank));
        CREATE TABLE IF NOT EXISTS pages(run_id INTEGER, url TEXT, observed_at TEXT, kind TEXT,
          status TEXT, evidence TEXT, raw TEXT, PRIMARY KEY(run_id,url,kind));
        CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY, run_id INTEGER, kind TEXT,
          timestamp TEXT, status INTEGER, cost REAL, error TEXT, raw TEXT, billable INTEGER);
        CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, timestamp TEXT, raw TEXT);
        CREATE TABLE IF NOT EXISTS imports(id INTEGER PRIMARY KEY, source TEXT, timestamp TEXT, raw TEXT);
        """)
        # Preserve existing audit databases when upgrading the request ledger.
        columns={row[1] for row in self.db.execute('PRAGMA table_info(requests)')}
        for name,kind in [('raw','TEXT'),('billable','INTEGER')]:
            if name not in columns:self.db.execute(f'ALTER TABLE requests ADD COLUMN {name} {kind}')
        self.db.commit()
    def execute(self, sql, args=()):
        cur=self.db.execute(sql,args);self.db.commit();return cur
    def rows(self,sql,args=()):
        return [dict(x) for x in self.db.execute(sql,args)]
    def start(self, fingerprint, manifest):
        return self.execute('INSERT INTO runs(started,fingerprint,manifest,status) VALUES(?,?,?,?)',
            (now(),fingerprint,json.dumps(manifest,ensure_ascii=False),'running')).lastrowid
    def finish(self,run,status):
        self.execute('UPDATE runs SET finished=?,status=? WHERE id=?',(now(),status,run))
    def search(self,run,q,status,error=None,raw=None,observed_at=None,cache_hit=False):
        self.execute('INSERT OR REPLACE INTO searches VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (run,q['id'],q['query'],q['category'],int(q['branded']),q['language'],q['priority'],
             q['purchase_intent'],q['canada_relevance'],status,error,observed_at or now(),int(cache_hit),json.dumps(raw,ensure_ascii=False)))
    def result(self,run,qid,r):
        self.execute('INSERT INTO results VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (run,qid,r['rank'],r['title'],r['url'],r['domain'],r['snippet'],r['summary'],
            r['rerank_score'],r['authority_tier'],r['publication_date'],json.dumps(r['brands']),
            r['official_brand'],r['classification']))
    def page(self,run,url,kind,status,evidence,raw):
        self.execute('INSERT OR REPLACE INTO pages VALUES(?,?,?,?,?,?,?)',
            (run,url,now(),kind,status,json.dumps(evidence,ensure_ascii=False),raw))
