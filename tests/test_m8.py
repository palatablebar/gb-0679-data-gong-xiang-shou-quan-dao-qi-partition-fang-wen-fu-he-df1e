from app.modules.m8_seals.rules import evaluate
from app.errors import DomainError
import pytest
def coverage_of(result): return {"coverage": result["stages"][6]}
def test_real_sample_archive_ready(result): assert result["stages"][7]["metrics"]["ready"] is True
def test_real_sample_archive_source_count(result): assert result["stages"][7]["metrics"]["source_lines"]==result["stages"][5]["metrics"]["accepted_inputs"]
def test_real_sample_seal_stable(result):
    rows=result["stages"][6]["rows"];ctx=coverage_of(result)
    assert evaluate(rows,ctx)["metrics"]["sha256"]==evaluate(rows,ctx)["metrics"]["sha256"]
def test_real_sample_seal_records_coverage(result): assert result["stages"][7]["metrics"]["coverage_id"]==result["stages"][6]["conclusion"]["coverage_id"]
def test_unbalanced_blocked():
    with pytest.raises(DomainError) as e:evaluate([],{"reconcile":{"metrics":{"balanced":False}}})
    assert e.value.code=="UNBALANCED"
def test_duplicate_archive_key():
    with pytest.raises(DomainError):evaluate([{"event_id":"1"},{"event_id":"1"}],{})
def test_seal_requires_coverage_conclusion():
    with pytest.raises(DomainError) as e:evaluate([{"event_id":"1"}],{})
    assert e.value.code=="NO_COVERAGE"
def test_seal_rejects_detached_row(result):
    "行未链接到本份覆盖结论时封存拒绝"
    rows=[{**r,"coverage":{}} for r in result["stages"][6]["rows"]]
    with pytest.raises(DomainError) as e:evaluate(rows,coverage_of(result))
    assert e.value.code=="SEAL_BASIS_BROKEN"
def test_seal_rejects_contradicting_row(result):
    "行内判定与覆盖结论冲突时封存拒绝"
    rows=[dict(r) for r in result["stages"][6]["rows"]]
    rows[0]["expected"]="1" if rows[0]["expected"]=="0" else "0"
    with pytest.raises(DomainError) as e:evaluate(rows,coverage_of(result))
    assert e.value.code=="SEAL_BASIS_BROKEN"
def test_real_sample_manifest_has_hash(result): assert len(result["manifest"]["input_sha256"])==64
def test_real_sample_export_rows_match(result): assert result["stages"][7]["rows"]==result["stages"][6]["rows"]
