"""
HTTP trigger + HTML reports UI for the SSH self-healing demo.

Postman:  POST http://localhost:8000/trigger/heal
Browser:  http://localhost:8000/   (report list)
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from config import load_config

BASE_DIR = Path(__file__).resolve().parent
REPORTS_DIR = BASE_DIR / "reports"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="SSH Self-Healing Demo API",
    description="Trigger self-healing and browse generated reports",
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_SAFE_ID = re.compile(r"^[\w.\-]+$")


class HealTriggerRequest(BaseModel):
    alert: str = Field(default="ServiceProcessDown", description="Alert type / name")
    service_name: str | None = Field(
        default=None, description="Override SERVICE_NAME from .env"
    )
    severity: str = Field(default="critical")
    host: str | None = Field(default=None, description="Optional source host label")
    message: str | None = Field(default=None)


def _reports_dir() -> Path:
    config = load_config()
    path = Path(config.reports_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _status_label(report: dict[str, Any]) -> str:
    final = report.get("final_status")
    if isinstance(final, dict):
        final = final.get("state") or final.get("active_state") or str(final)
    final_s = str(final or "").lower()
    if "active" in final_s and "inactive" not in final_s:
        return "healed"
    if "inactive" in final_s or "failed" in final_s or "dead" in final_s:
        return "failed"
    ver = report.get("verification_result")
    if isinstance(ver, dict) and ver.get("is_active") is True:
        return "healed"
    if report.get("initial_status") and not final:
        return "checked"
    return "unknown"


def _list_reports() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted(_reports_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        # Keep healing-summary.json as "latest" alias only — not a list entry
        if path.name in {".gitkeep", "healing-summary.json"}:
            continue
        try:
            data = _load_report(path)
        except (json.JSONDecodeError, OSError):
            continue
        report_id = path.stem
        if data.get("report_id"):
            report_id = str(data["report_id"])
        items.append(
            {
                "id": report_id,
                "filename": path.name,
                "timestamp": data.get("timestamp")
                or datetime.fromtimestamp(path.stat().st_mtime).isoformat(
                    timespec="seconds"
                ),
                "service_name": _as_text(data.get("service_name")),
                "ssh_host": _as_text(data.get("ssh_host")),
                "initial_status": _as_text(data.get("initial_status")),
                "final_status": _as_text(data.get("final_status")),
                "status": _status_label(data),
            }
        )
    return items


def _resolve_report_path(report_id: str) -> Path:
    if not _SAFE_ID.match(report_id):
        raise HTTPException(status_code=400, detail="Invalid report id")
    reports = _reports_dir()
    candidates = [
        reports / f"{report_id}.json",
        reports / report_id,
    ]
    for path in candidates:
        if path.is_file() and path.suffix.lower() == ".json":
            return path
    # Fallback: match by report_id field inside JSON
    for path in reports.glob("*.json"):
        try:
            data = _load_report(path)
        except (json.JSONDecodeError, OSError):
            continue
        if str(data.get("report_id", "")) == report_id or path.stem == report_id:
            return path
    raise HTTPException(status_code=404, detail="Report not found")


def _as_text(value: Any, fallback: str = "—") -> str:
    if value is None or value == "":
        return fallback
    if isinstance(value, dict):
        for key in ("state", "active_state", "status", "result", "detail"):
            if value.get(key) not in (None, ""):
                return str(value[key])
        return json.dumps(value)
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    return str(value)


def _normalize_actions(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raw = [raw]
    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            entry = dict(item)
            entry.setdefault("step", idx)
            entry.setdefault("action", entry.get("command") or entry.get("detail") or "Action")
            normalized.append(entry)
        else:
            normalized.append({"step": idx, "action": str(item), "result": ""})
    return normalized


def _normalize_recommendations(raw: Any) -> list[dict[str, str]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raw = [raw]
    out: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(
                {
                    "priority": str(item.get("priority") or ""),
                    "item": str(item.get("item") or item.get("title") or "Recommendation"),
                    "detail": str(item.get("detail") or item.get("description") or ""),
                }
            )
        else:
            out.append({"priority": "", "item": "Recommendation", "detail": str(item)})
    return out


def _normalize_log_evidence(raw: Any) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        if raw is None:
            return {}
        return {"evidence": [str(raw)]}
    out: dict[str, list[str]] = {}
    for key, value in raw.items():
        if isinstance(value, list):
            out[str(key)] = [str(v) for v in value]
        elif value is None:
            out[str(key)] = []
        else:
            out[str(key)] = [str(value)]
    return out


def _normalize_verification(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {str(k): _as_text(v) for k, v in raw.items()}
    return {"result": _as_text(raw)}


def _detail_context(report: dict[str, Any], report_id: str) -> dict[str, Any]:
    root = report.get("root_cause_analysis")
    if not isinstance(root, dict):
        root = {"detail": _as_text(root, "No root cause recorded.")}
    else:
        root = {
            "failure_type": _as_text(root.get("failure_type"), ""),
            "detail": _as_text(
                root.get("detail")
                or root.get("probable_cause")
                or root.get("finding"),
                "No root cause recorded.",
            ),
        }

    alert = report.get("alert") if isinstance(report.get("alert"), dict) else {}

    return {
        "report_id": report_id,
        "timestamp": _as_text(report.get("timestamp")),
        "service_name": _as_text(report.get("service_name")),
        "ssh_host": _as_text(report.get("ssh_host")),
        "status": _status_label(report),
        "initial_status": _as_text(report.get("initial_status")),
        "final_status": _as_text(report.get("final_status")),
        "alert": {
            "alert": _as_text(alert.get("alert"), "—"),
            "severity": _as_text(alert.get("severity"), "—"),
        },
        "root_cause": root,
        "actions": _normalize_actions(report.get("actions_taken")),
        "verification": _normalize_verification(report.get("verification_result")),
        "log_evidence": _normalize_log_evidence(report.get("log_evidence")),
        "recommendations": _normalize_recommendations(report.get("recommendations")),
        "raw_json": json.dumps(
            {k: v for k, v in report.items() if k != "agent_response"},
            indent=2,
            default=str,
        ),
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/trigger/heal")
def trigger_heal(body: HealTriggerRequest) -> JSONResponse:
    """Postman / monitoring webhook entrypoint."""
    from self_healing_agent import SSHSelfHealingAgent

    config = load_config()
    if body.service_name:
        config.service_name = body.service_name

    alert = {
        "alert": body.alert,
        "service_name": config.service_name,
        "severity": body.severity,
        "host": body.host or config.ssh_host,
        "message": body.message
        or f"{body.alert}: {config.service_name} reported down",
    }

    agent = SSHSelfHealingAgent(config)
    summary = agent.execute_healing(alert=alert)
    public = {k: v for k, v in summary.items() if k != "agent_response"}
    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "report_id": summary.get("report_id"),
            "report_url": f"/reports/{summary.get('report_id')}",
            "summary": public,
        },
    )


@app.get("/api/reports")
def api_list_reports() -> dict[str, Any]:
    return {"reports": _list_reports()}


@app.get("/api/reports/{report_id}")
def api_get_report(report_id: str) -> dict[str, Any]:
    path = _resolve_report_path(report_id)
    data = _load_report(path)
    data.pop("agent_response", None)
    return data


@app.get("/", response_class=HTMLResponse)
def reports_home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {"reports": _list_reports()},
    )


@app.get("/reports/{report_id}", response_class=HTMLResponse)
def report_detail(request: Request, report_id: str) -> HTMLResponse:
    path = _resolve_report_path(report_id)
    data = _load_report(path)
    rid = str(data.get("report_id") or path.stem)
    ctx = _detail_context(data, rid)
    return templates.TemplateResponse(request, "report.html", ctx)


def main() -> None:
    import uvicorn

    config = load_config()
    uvicorn.run(
        "api_server:app",
        host=config.api_host,
        port=config.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
