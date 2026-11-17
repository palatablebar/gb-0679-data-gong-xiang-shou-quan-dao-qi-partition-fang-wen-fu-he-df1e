import hashlib,json
from app.config import RULE_VERSION
from app.errors import DomainError
from app.reasons import sources
from app.values import instant,scalar
from app.modules.m3_grants.rules import GRANTS,validate_grants
from app.modules.m4_conflicts.rules import decide
STATUS_LABEL={"allow":"覆盖内","deny":"显式拒绝","gap":"覆盖空档"}
def resolve_scope(rows,grants,params):
    "复查范围：parameters.scope 显式给定，否则取访问时刻与授权窗的并集边界。"
    given=params.get("scope")
    if given is not None:
        if not isinstance(given,dict): raise DomainError("BAD_SCOPE","复查范围需要对象")
        start,end=instant(given["start"]),instant(given["end"])
    else:
        points=[instant(g[k]) for g in grants for k in ("start","end")]+[instant(r["at"]) for r in rows]
        if not points: raise DomainError("BAD_SCOPE","无法确定复查范围")
        start,end=min(points),max(points)
    if not start<end: raise DomainError("BAD_SCOPE","复查范围无效")
    return start,end
def sweep_intervals(grants,partition,scope):
    "连续有效区间（权威结论）：在授权窗边界切段，复用冲突裁决，相邻同态段合并。"
    start,end=scope;points={start,end}
    for g in grants:
        s,e=max(instant(g["start"]),start),min(instant(g["end"]),end)
        if s<e: points.update((s,e))
    ordered=sorted(points);merged=[]
    for a,b in zip(ordered,ordered[1:]):
        candidates=[g for g in grants if instant(g["start"])<=a<instant(g["end"])]
        hit=decide(candidates,partition)
        status="deny" if hit["deny_rules"] else ("allow" if hit["allow_rules"] else "gap")
        interval={"start":a,"end":b,"status":status,"rules":hit["matched_rules"],"deny_rules":hit["deny_rules"],"allow_rules":hit["allow_rules"]}
        if merged and merged[-1]["status"]==status and merged[-1]["rules"]==interval["rules"]: merged[-1]["end"]=b
        else: merged.append(interval)
    return merged
def project_months(intervals,scope):
    "按月展开只是连续区间在自然月边界上的裁剪投影：跨月拒绝不扩整月、不重复计。"
    _,end=scope;cur=scope[0].replace(day=1,hour=0,minute=0,second=0,microsecond=0);months=[]
    while cur<end:
        nxt=cur.replace(year=cur.year+1,month=1) if cur.month==12 else cur.replace(month=cur.month+1)
        slices=[{"start":max(iv["start"],cur),"end":min(iv["end"],nxt),"status":iv["status"],"rules":iv["rules"]} for iv in intervals if iv["start"]<nxt and iv["end"]>cur]
        months.append({"month":cur.strftime("%Y-%m"),"slices":slices,"has_gap":any(s["status"]=="gap" for s in slices)})
        cur=nxt
    return months
def interval_at(intervals,at):
    for iv in intervals:
        if iv["start"]<=at<iv["end"]: return iv
    return None
def lookup_status(conclusion,principal,resource,partition,at):
    "封存复核用：从结论中定位(主体,资源,分区,时刻)的覆盖状态。"
    at=instant(at)
    for pair in conclusion["pairs"]:
        if pair["principal"]==principal and pair["resource"]==resource:
            entry=pair["partitions"].get(partition)
            if not entry: return None
            hit=interval_at([{"start":instant(i["start"]),"end":instant(i["end"]),"status":i["status"]} for i in entry["intervals"]],at)
            return hit["status"] if hit else None
    return None
def evaluate(rows,context):
    params=context.get("parameters",{}) if isinstance(context,dict) else {}
    grants=validate_grants(params.get("grants",GRANTS))
    scope=resolve_scope(rows,grants,params)
    start,end=scope
    for row in rows:
        if not start<=instant(row["at"])<end: raise DomainError("BAD_SCOPE","复查范围未覆盖全部访问")
    pair_keys=sorted({(r["principal"],r["resource"]) for r in rows}|{(g["principal"],g["resource"]) for g in grants})
    pairs=[];interval_index={}
    for principal,resource in pair_keys:
        own=[g for g in grants if g["principal"]==principal and g["resource"]==resource]
        partitions=sorted({r["partition"] for r in rows if (r["principal"],r["resource"])==(principal,resource)})
        pmap={};gaps=[]
        for part in partitions:
            intervals=sweep_intervals(own,part,scope)
            pmap[part]={"intervals":intervals,"months":project_months(intervals,scope)}
            interval_index[(principal,resource,part)]=intervals
            gaps+=[{"partition":part,"start":iv["start"],"end":iv["end"]} for iv in intervals if iv["status"]=="gap"]
        pairs.append({"principal":principal,"resource":resource,"partitions":pmap,"gaps":gaps})
    links=[];annotated=[]
    for row in rows:
        at=instant(row["at"]);key=(row["principal"],row["resource"],row["partition"])
        hit=interval_at(interval_index[key],at);status=hit["status"]
        evidence=hit["rules"] or ["NO_GRANT"]
        violation=row.get("observed")=="allowed" and status!="allow"
        if violation: links.append({"event_id":row.get("event_id"),"principal":row["principal"],"resource":row["resource"],"partition":row["partition"],"at":row["at"],"status":status,"interval":{"start":hit["start"],"end":hit["end"]},"evidence":evidence,"sources":sources(row)})
        annotated.append({**row,"coverage":{"coverage_id":"","status":status,"interval":{"start":hit["start"],"end":hit["end"]},"evidence":evidence},"coverage_status":STATUS_LABEL[status],"coverage_violation":"越权访问" if violation else "","coverage_evidence":" / ".join(evidence)})
    conclusion=scalar({"rule_version":RULE_VERSION,"scope":{"start":start,"end":end},"pairs":pairs,"links":links})
    coverage_id="cov-"+hashlib.sha256(json.dumps(conclusion,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
    conclusion["coverage_id"]=coverage_id
    for row in annotated: row["coverage"]["coverage_id"]=coverage_id
    metrics={"pairs":len(pairs),"gap_intervals":sum(len(p["gaps"]) for p in pairs),"gap_months":sum(m["has_gap"] for p in pairs for v in p["partitions"].values() for m in v["months"]),"linked_violations":len(links),"gap_violations":sum(l["status"]=="gap" for l in links),"coverage_id":coverage_id,"scope_start":conclusion["scope"]["start"],"scope_end":conclusion["scope"]["end"]}
    return {"rows":annotated,"quarantine":[],"metrics":metrics,"conclusion":conclusion}
