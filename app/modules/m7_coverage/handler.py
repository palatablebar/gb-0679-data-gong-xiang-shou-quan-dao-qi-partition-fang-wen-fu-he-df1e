from flask import Blueprint,request,jsonify
from app.errors import DomainError
from app.pipeline import stage_preview
from app import store
bp=Blueprint("coverage",__name__)
@bp.route("/api/coverage",methods=["GET","POST"])
def preview():
    payload=request.get_json(silent=True) if request.method=="POST" else {}
    if payload is None or not isinstance(payload,dict): raise DomainError("BAD_BODY","请求需要对象")
    return jsonify(stage_preview(6,payload))
@bp.get("/api/coverage/current")
def current(): return jsonify(store.current_coverage())
@bp.get("/api/coverage/versions")
def versions(): return {"versions":store.coverage_history()}
@bp.get("/api/coverage/<coverage_id>")
def detail(coverage_id): return jsonify(store.get_coverage(coverage_id))
@bp.post("/api/coverage/switch")
def switch():
    payload=request.get_json(silent=True)
    if not isinstance(payload,dict): raise DomainError("BAD_BODY","请求需要对象")
    if not isinstance(payload.get("coverage_id"),str) or not isinstance(payload.get("version"),int): raise DomainError("BAD_VERSION","请提供覆盖版本与版本号")
    return jsonify(store.switch_coverage(payload["coverage_id"],payload["version"]))
