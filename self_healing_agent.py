"""
SSH Self-Healing Agent

Runs on Windows, connects to a remote Linux host (or WSL) via Strands SshSandbox,
and follows the DEMO_FLOW workflow: status → logs → stop/start → verify → summary.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from strands import Agent
from strands.sandbox.ssh import SshSandbox

from config import SSHServiceConfig, load_config


def _report_filename(service_name: str, when: datetime | None = None) -> str:
    stamp = (when or datetime.now()).strftime("%Y%m%d-%H%M%S")
    safe = "".join(c if c.isalnum() or c in "._-" else "-" for c in service_name)
    return f"healing-{safe}-{stamp}.json"


def _save_summary_locally(
    path: str,
    summary: dict[str, Any],
    *,
    also_latest: str | None = None,
) -> str:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(summary, indent=2)
    out.write_text(payload, encoding="utf-8")
    if also_latest:
        latest = Path(also_latest)
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(payload, encoding="utf-8")
    return str(out.resolve())


class SSHSelfHealingAgent:
    """Self-healing agent that remediates a remote systemd service over SSH."""

    def __init__(self, config: SSHServiceConfig):
        self.config = config

        self.ssh_sandbox = SshSandbox(
            host=config.ssh_host,
            working_dir=config.ssh_working_dir,
            identity_file=config.ssh_identity_file,
            port=config.ssh_port,
            allow_unknown_hosts=config.allow_unknown_hosts,
        )

        self.agent = Agent(
            sandbox=self.ssh_sandbox,
            description=(
                "You are a Linux Service Reliability Engineer agent. Your role is to:\n"
                "1. Diagnose systemd service health on a remote host over SSH\n"
                "2. Read journal and application logs to identify root causes\n"
                "3. Stop and start services that are inactive or failed\n"
                "4. Verify successful recovery (active/running + healthy log lines)\n"
                "5. Produce a clear summary of findings and actions\n\n"
                "IMPORTANT RULES:\n"
                "- Always check service status before restarting\n"
                "- Only stop/start if the service is inactive, failed, or clearly unhealthy\n"
                "- Always verify Active: active (running) after restart\n"
                "- Look for startup confirmation in logs "
                "(e.g. 'started successfully', 'Server listening', health 200 OK)\n"
                "- Do not run unrelated or destructive commands\n"
            ),
        )

    def execute_healing(self, alert: dict[str, Any] | None = None) -> dict[str, Any]:
        service = self.config.service_name
        log_file = self.config.log_file_path
        started = datetime.now()
        reports_dir = Path(self.config.reports_dir)
        report_name = _report_filename(service, started)
        summary_path = reports_dir / report_name
        latest_path = Path(self.config.summary_output_path)

        if alert and alert.get("service_name"):
            service = str(alert["service_name"])

        instruction = f"""
Execute a self-healing operation for the remote systemd service '{service}'.

You already have SSH shell tools connected to the target host. Do NOT open a new SSH client manually.

WORKFLOW:
1. Check whether the service is running:
   - systemctl is-active {service}
   - systemctl status {service} --no-pager
2. Read recent logs:
   - journalctl -u {service} -n 50 --no-pager
   - If readable, also read the last lines of {log_file}
3. Identify the failure reason from the logs (if any).
4. If the service is inactive or failed:
   - Use: sudo -n systemctl stop {service}
   - Use: sudo -n systemctl start {service}
   - Prefer sudo -n (non-interactive). Do NOT use wsl.exe -u root or Windows interop.
   - Wait a few seconds for startup
5. Verify recovery:
   - systemctl is-active {service} should be 'active'
   - systemctl status {service} --no-pager should show Active: active (running)
   - Confirm recent logs show successful startup / health (no new FATAL/ERROR after restart)
6. Return a JSON summary object with these fields:
   - timestamp
   - service_name
   - initial_status
   - root_cause_analysis
   - actions_taken
   - final_status
   - verification_result
   - log_evidence (short quotes from failure and recovery logs)
   - recommendations

If the service is already active and healthy, document that and skip restart.
If restart fails after {self.config.max_retry_attempts} attempts, document the failure clearly.
"""

        print("=" * 80)
        print("SSH Self-Healing Operation")
        print(f"  Target : {self.config.ssh_host}:{self.config.ssh_port}")
        print(f"  Service: {service}")
        print(f"  Started: {started.isoformat(timespec='seconds')}")
        print("=" * 80)

        response = self.agent(instruction)
        response_text = str(response)

        summary: dict[str, Any] = {
            "timestamp": started.isoformat(timespec="seconds"),
            "service_name": service,
            "ssh_host": self.config.ssh_host,
            "report_id": report_name.replace(".json", ""),
            "alert": alert or {},
            "agent_response": response_text,
            "summary_output_path": str(summary_path),
        }

        # Prefer JSON block from the model if present
        try:
            start = response_text.find("{")
            end = response_text.rfind("}")
            if start != -1 and end != -1 and end > start:
                parsed = json.loads(response_text[start : end + 1])
                if isinstance(parsed, dict):
                    # Keep identity fields from this run
                    alert_meta = summary.get("alert")
                    report_id = summary.get("report_id")
                    summary.update(parsed)
                    summary["report_id"] = report_id
                    summary["ssh_host"] = self.config.ssh_host
                    summary["alert"] = alert_meta
                    summary["summary_output_path"] = str(summary_path)
                    if "agent_response" not in summary:
                        summary["agent_response"] = response_text
        except json.JSONDecodeError:
            pass

        saved = _save_summary_locally(
            str(summary_path),
            summary,
            also_latest=str(latest_path),
        )
        summary["summary_output_path"] = saved
        print(f"\nSummary saved to: {saved}")
        return summary


def main() -> int:
    config = load_config()

    if len(sys.argv) >= 2:
        config.service_name = sys.argv[1]
    if len(sys.argv) >= 3:
        config.ssh_host = sys.argv[2]

    agent = SSHSelfHealingAgent(config)
    result = agent.execute_healing()
    print("\nDone.")
    print(json.dumps({k: v for k, v in result.items() if k != "agent_response"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
