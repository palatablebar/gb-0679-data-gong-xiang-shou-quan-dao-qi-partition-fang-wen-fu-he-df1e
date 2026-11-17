import csv,io
from app.pipeline import execute,load_sample
from app import store
def test_full_sample_flow(client):
    r=client.post("/api/runs",json={"sample":"dirty.csv"});assert r.status_code==200
    p=r.get_json();assert len(p["stages"])==8
    assert p["stages"][5]["metrics"]["balanced"] is True
    assert p["stages"][6]["metrics"]["coverage_id"]==p["stages"][7]["metrics"]["coverage_id"]
def test_idempotent_real_input(sample):
    a=execute(sample);b=execute(sample)
    assert a["run_id"]==b["run_id"] and len(store.history())==1
def test_stale_review_409(client):
    "TRAP-26 陈旧复核不得覆盖新版本"
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json();u="/api/runs/"+p["run_id"]+"/review"
    assert client.post(u,json={"version":1,"decision":"已复核"}).status_code==200
    assert client.post(u,json={"version":1,"decision":"退回复核"}).status_code==409
def test_export_has_manifest_and_quarantine(client):
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json()
    r=client.get("/api/runs/"+p["run_id"]+"/archive")
    rows=list(csv.reader(io.StringIO(r.data.decode("utf-8-sig"))))
    assert rows[0][1]=="input_sha256" and any(x[3]=="quarantine" for x in rows[1:])
    assert rows[0][7]=="coverage_id" and all(x[7]==p["stages"][6]["metrics"]["coverage_id"] for x in rows[1:])
def test_coverage_version_endpoints(client):
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json()
    current=client.get("/api/coverage/current").get_json()
    assert current["coverage_id"]==p["stages"][6]["metrics"]["coverage_id"] and current["version"]==1
    assert client.post("/api/runs",json={"sample":"dirty.csv","parameters":{"scope":{"start":"2026-11-01T00:00:00Z","end":"2027-01-01T00:00:00Z"}}}).status_code==200
    versions=client.get("/api/coverage/versions").get_json()["versions"]
    assert len(versions)==2 and sum(v["active"] for v in versions)==1
    stale=client.post("/api/coverage/switch",json={"coverage_id":versions[0]["coverage_id"],"version":9})
    assert stale.status_code==409
    assert client.get("/api/coverage/current").get_json()["coverage_id"]==current["coverage_id"]
    target=[v for v in versions if not v["active"]][0]
    ok=client.post("/api/coverage/switch",json={"coverage_id":target["coverage_id"],"version":1})
    assert ok.status_code==200 and ok.get_json()["version"]==2
    assert client.get("/api/coverage/"+current["coverage_id"]).status_code==200
def test_coverage_switch_missing_404(client): assert client.post("/api/coverage/switch",json={"coverage_id":"cov-none","version":1}).status_code==404
def test_failed_import_is_atomic(client):
    assert client.post("/api/runs",json={"csv":"bad"}).status_code==422
    assert store.history()==[]
def test_module_entrances(client):
    from app.config import MODULES
    for slug,name in MODULES:
        assert client.get("/api/"+slug).status_code==200
        assert client.get("/"+slug).status_code==200
def test_missing_run_404(client): assert client.get("/api/runs/missing").status_code==404
