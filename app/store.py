import sqlite3,json
from pathlib import Path
from app.config import DATA_DIR
from app.errors import DomainError
def connect():
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(DATA_DIR/"records.db",timeout=20)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY,payload TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,decision TEXT NOT NULL DEFAULT '待复核')")
    db.execute("CREATE TABLE IF NOT EXISTS coverage (id TEXT PRIMARY KEY,payload TEXT NOT NULL,run_id TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS coverage_pointer (scope TEXT PRIMARY KEY,coverage_id TEXT NOT NULL,version INTEGER NOT NULL)")
    return db
def save(run_id,payload,conclusion=None):
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO runs(id,payload) VALUES (?,?)",(run_id,json.dumps(payload,ensure_ascii=False)))
        if conclusion:
            db.execute("INSERT OR IGNORE INTO coverage(id,payload,run_id) VALUES (?,?,?)",(conclusion["coverage_id"],json.dumps(conclusion,ensure_ascii=False),run_id))
            db.execute("INSERT OR IGNORE INTO coverage_pointer(scope,coverage_id,version) VALUES ('current',?,1)",(conclusion["coverage_id"],))
    return get(run_id)
def get_coverage(coverage_id):
    with connect() as db: row=db.execute("SELECT payload,run_id FROM coverage WHERE id=?",(coverage_id,)).fetchone()
    if not row: raise DomainError("NOT_FOUND","覆盖版本不存在",404)
    return {"coverage_id":coverage_id,"run_id":row[1],"conclusion":json.loads(row[0])}
def current_coverage():
    with connect() as db: row=db.execute("SELECT coverage_id,version FROM coverage_pointer WHERE scope='current'").fetchone()
    if not row: raise DomainError("NOT_FOUND","尚无生效覆盖结论",404)
    return {**get_coverage(row[0]),"version":row[1]}
def coverage_history():
    with connect() as db:
        current=db.execute("SELECT coverage_id FROM coverage_pointer WHERE scope='current'").fetchone()
        active=current[0] if current else None
        return [{"coverage_id":i,"run_id":r,"active":i==active} for i,r in db.execute("SELECT id,run_id FROM coverage ORDER BY rowid DESC")]
def switch_coverage(coverage_id,version):
    "切换生效覆盖版本：版本条件更新，冲突时旧版结论与证据原样保留。"
    with connect() as db:
        if not db.execute("SELECT 1 FROM coverage WHERE id=?",(coverage_id,)).fetchone(): raise DomainError("NOT_FOUND","覆盖版本不存在",404)
        cursor=db.execute("UPDATE coverage_pointer SET coverage_id=?,version=version+1 WHERE scope='current' AND version=?",(coverage_id,version))
        if cursor.rowcount!=1:
            if not db.execute("SELECT 1 FROM coverage_pointer WHERE scope='current'").fetchone(): raise DomainError("NOT_FOUND","尚无生效覆盖结论",404)
            raise DomainError("STALE_VERSION","覆盖版本已更新，请刷新",409)
    return current_coverage()
def get(run_id):
    with connect() as db: row=db.execute("SELECT payload,version,decision FROM runs WHERE id=?",(run_id,)).fetchone()
    if not row: raise DomainError("NOT_FOUND","批次不存在",404)
    return {**json.loads(row[0]),"version":row[1],"decision":row[2]}
def latest():
    with connect() as db: row=db.execute("SELECT id FROM runs ORDER BY rowid DESC LIMIT 1").fetchone()
    return get(row[0]) if row else None
def history():
    with connect() as db: return [{"run_id":i,"version":v,"decision":d} for i,v,d in db.execute("SELECT id,version,decision FROM runs ORDER BY rowid DESC")]
def review(run_id,version,decision):
    if decision not in {"已复核","退回复核"}: raise DomainError("BAD_DECISION","复核状态无效")
    with connect() as db:
        cursor=db.execute("UPDATE runs SET version=version+1,decision=? WHERE id=? AND version=?",(decision,run_id,version))
        if cursor.rowcount!=1:
            if not db.execute("SELECT 1 FROM runs WHERE id=?",(run_id,)).fetchone(): raise DomainError("NOT_FOUND","批次不存在",404)
            raise DomainError("STALE_VERSION","版本已更新，请刷新",409)
    return get(run_id)
