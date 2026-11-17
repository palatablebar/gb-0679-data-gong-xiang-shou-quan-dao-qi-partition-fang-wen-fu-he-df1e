import pytest
from datetime import datetime,timezone,timedelta
from app.errors import DomainError
from app.pipeline import execute,load_sample
from app import store
from app.modules.m7_coverage.rules import evaluate,lookup_status
def access(event_id="E1",principal="analyst",resource="orders",partition="2026-10",at="2026-11-05T00:00:00+00:00",observed="allowed"):
    return {"event_id":event_id,"principal":principal,"resource":resource,"partition":partition,"at":at,"observed":observed,"_line":1,"_sources":[1]}
def grant(id="G-A",principal="analyst",resource="orders",start="2026-11-01T00:00:00Z",end="2026-11-10T00:00:00Z",frm="2026-01",to="2026-12",effect="allow"):
    return {"id":id,"principal":principal,"resource":resource,"start":start,"end":end,"from_partition":frm,"to_partition":to,"effect":effect}
def ctx(grants,scope=None):
    params={"grants":grants}
    if scope: params["scope"]=scope
    return {"parameters":params}
def ts(text): return datetime.fromisoformat(text.replace("Z","+00:00")).astimezone(timezone.utc)
def test_gap_visible_without_access_inside():
    "空档内没有任何访问时，整段空档仍要出现在结论里"
    grants=[grant("G-A",end="2026-11-10T00:00:00Z"),grant("G-B",start="2026-11-20T00:00:00Z",end="2026-12-01T00:00:00Z")]
    r=evaluate([access()],ctx(grants,{"start":"2026-11-01T00:00:00Z","end":"2026-12-01T00:00:00Z"}))
    gaps=[i for i in r["conclusion"]["pairs"][0]["partitions"]["2026-10"]["intervals"] if i["status"]=="gap"]
    assert len(gaps)==1 and gaps[0]["start"]=="2026-11-10T00:00:00+00:00" and gaps[0]["end"]=="2026-11-20T00:00:00+00:00"
    assert r["metrics"]["gap_intervals"]==1 and r["conclusion"]["links"]==[]
def test_alias_deny_covers_canonical_resource():
    "别名登记的拒绝必须先归并再算覆盖，不得静默失效"
    grants=[grant("G-A",end="2026-12-01T00:00:00Z"),grant("G-D",resource="订单",start="2026-11-10T00:00:00Z",end="2026-11-20T00:00:00Z",frm="2026-10",to="2026-11",effect="deny")]
    r=evaluate([access(at="2026-11-16T00:00:00+00:00")],ctx(grants))
    assert r["rows"][0]["coverage_status"]=="显式拒绝" and "G-D" in r["rows"][0]["coverage"]["evidence"]
    assert all(p["resource"]!="订单" for p in r["conclusion"]["pairs"])
def test_cross_month_deny_projection():
    "跨月拒绝：连续区间保持一段，按月展开只裁剪不扩月"
    grants=[grant("G-A",end="2027-01-01T00:00:00Z"),grant("G-D",start="2026-11-25T00:00:00Z",end="2026-12-05T00:00:00Z",effect="deny")]
    r=evaluate([access()],ctx(grants,{"start":"2026-11-01T00:00:00Z","end":"2027-01-01T00:00:00Z"}))
    entry=r["conclusion"]["pairs"][0]["partitions"]["2026-10"]
    denies=[i for i in entry["intervals"] if i["status"]=="deny"]
    assert len(denies)==1 and denies[0]["start"]=="2026-11-25T00:00:00+00:00" and denies[0]["end"]=="2026-12-05T00:00:00+00:00"
    months={m["month"]:m for m in entry["months"]}
    nov=[s for s in months["2026-11"]["slices"] if s["status"]=="deny"]
    dec=[s for s in months["2026-12"]["slices"] if s["status"]=="deny"]
    assert (nov[0]["start"],nov[0]["end"])==("2026-11-25T00:00:00+00:00","2026-12-01T00:00:00+00:00")
    assert (dec[0]["start"],dec[0]["end"])==("2026-12-01T00:00:00+00:00","2026-12-05T00:00:00+00:00")
    span=sum((ts(s["end"])-ts(s["start"]) for s in nov+dec),timedelta(0))
    assert span==ts(denies[0]["end"])-ts(denies[0]["start"])
def test_months_are_exact_projection_of_intervals(result):
    "任一主体/资源/分区：按月切片合并回去必须等于连续区间"
    for pair in result["stages"][6]["conclusion"]["pairs"]:
        for entry in pair["partitions"].values():
            merged=[]
            for m in entry["months"]:
                for s in m["slices"]:
                    key=(s["status"],tuple(s["rules"]))
                    if merged and merged[-1][0]==key and merged[-1][1]["end"]==s["start"]: merged[-1][1]["end"]=s["end"]
                    else: merged.append([key,{"start":s["start"],"end":s["end"]}])
            assert [(k,dict(v)) for k,v in merged]==[((i["status"],tuple(i["rules"])),{"start":i["start"],"end":i["end"]}) for i in entry["intervals"]]
def test_real_guest_gap_violation_linked(result):
    "落入空档的越权访问接到空档区间与证据"
    links=[l for l in result["stages"][6]["conclusion"]["links"] if l["principal"]=="guest"]
    assert links and all(l["status"]=="gap" and l["evidence"]==["NO_GRANT"] for l in links)
    assert links[0]["interval"]=={"start":"2026-11-01T00:00:00+00:00","end":"2026-12-01T00:00:00+00:00"}
    row=[r for r in result["stages"][6]["rows"] if r["principal"]=="guest"][0]
    assert row["coverage_status"]=="覆盖空档" and row["coverage_violation"]=="越权访问"
def test_real_deny_violation_linked(result):
    links=[l for l in result["stages"][6]["conclusion"]["links"] if l["status"]=="deny"]
    assert links and all("G-02" in l["evidence"] for l in links)
def test_real_sample_pairs_and_id(result):
    m=result["stages"][6]["metrics"]
    assert m["pairs"]==3 and m["coverage_id"].startswith("cov-") and m["gap_violations"]==8
def test_coverage_status_matches_row_effect(result):
    for row in result["stages"][6]["rows"]: assert (row["coverage"]["status"]=="allow")==(row["effect"]=="allow")
def test_lookup_status_roundtrip(result):
    conclusion=result["stages"][6]["conclusion"]
    assert lookup_status(conclusion,"analyst","orders","2026-10","2026-11-16T00:00:00Z")=="deny"
    assert lookup_status(conclusion,"analyst","orders","2026-09","2026-11-16T00:00:00Z")=="allow"
    assert lookup_status(conclusion,"nobody","orders","2026-10","2026-11-16T00:00:00Z") is None
def test_scope_must_cover_all_accesses():
    with pytest.raises(DomainError) as e: evaluate([access(at="2026-11-16T00:00:00+00:00")],ctx([grant("G-A",end="2026-12-01T00:00:00Z")],{"start":"2026-11-01T00:00:00Z","end":"2026-11-10T00:00:00Z"}))
    assert e.value.code=="BAD_SCOPE"
def test_scope_window_invalid():
    with pytest.raises(DomainError): evaluate([access()],ctx([grant("G-A")],{"start":"2026-12-01T00:00:00Z","end":"2026-11-01T00:00:00Z"}))
def test_same_input_adds_no_coverage_version(sample):
    execute(sample);execute(sample)
    assert len(store.coverage_history())==1
def test_first_coverage_auto_active(sample):
    execute(sample);current=store.current_coverage()
    assert current["version"]==1 and current["coverage_id"]==store.coverage_history()[0]["coverage_id"]
def test_switch_stale_keeps_old_evidence(sample):
    execute(sample);first=store.current_coverage()
    execute(sample,{"scope":{"start":"2026-11-01T00:00:00Z","end":"2027-01-01T00:00:00Z"}})
    second=[v for v in store.coverage_history() if not v["active"]][0]
    with pytest.raises(DomainError) as e: store.switch_coverage(second["coverage_id"],first["version"]+5)
    assert e.value.code=="STALE_VERSION"
    assert store.current_coverage()["coverage_id"]==first["coverage_id"]
    assert store.get_coverage(first["coverage_id"])["conclusion"]==first["conclusion"]
    updated=store.switch_coverage(second["coverage_id"],first["version"])
    assert updated["coverage_id"]==second["coverage_id"] and updated["version"]==first["version"]+1
    assert store.get_coverage(first["coverage_id"])["conclusion"]==first["conclusion"]
def test_switch_unknown_coverage_404(sample):
    execute(sample)
    with pytest.raises(DomainError) as e: store.switch_coverage("cov-missing",1)
    assert e.value.code=="NOT_FOUND"
