import hashlib,json
from app.errors import DomainError
from app.reasons import sources
from app.modules.m7_coverage.rules import lookup_status
def evaluate(rows,context):
    stages=[v for v in context.values() if isinstance(v,dict) and "metrics" in v]
    balances=[s["metrics"]["balanced"] for s in stages if "balanced" in s["metrics"]]
    if balances and not all(balances): raise DomainError("UNBALANCED","来源行未对平，不能归档")
    ids=[str(r.get("event_id",r.get("_line",""))) for r in rows]
    if len(ids)!=len(set(ids)): raise DomainError("ARCHIVE_DUPLICATE","归档业务键重复")
    coverage=context.get("coverage") if isinstance(context,dict) else None
    conclusion=coverage.get("conclusion") if isinstance(coverage,dict) else None
    if not conclusion: raise DomainError("NO_COVERAGE","缺少覆盖结论，不能封存")
    coverage_id=conclusion.get("coverage_id")
    for row in rows:
        link=row.get("coverage") or {}
        status=lookup_status(conclusion,row.get("principal"),row.get("resource"),row.get("partition"),row.get("at")) if link.get("coverage_id")==coverage_id else None
        if status is None or row.get("expected")!=("1" if status=="allow" else "0"): raise DomainError("SEAL_BASIS_BROKEN","访问依据与覆盖结论断开，不能封存")
    encoded=json.dumps(rows,ensure_ascii=False,sort_keys=True,default=str).encode()
    return {"rows":rows,"quarantine":[],"metrics":{"records":len(rows),"source_lines":len(set(x for row in rows for x in sources(row))),"sha256":hashlib.sha256(encoded).hexdigest(),"ready":True,"differences":sum(r.get("status")=="差异" for r in rows),"coverage_id":coverage_id}}
