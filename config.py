"""
Configuration for the SSH self-healing demo agent.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_CONFIG_DIR = Path(__file__).resolve().parent
_ENV_FILE = _CONFIG_DIR / ".env"


def _load_env() -> None:
    """Load .env from this package directory (not cwd), stripping BOM if present."""
    if _ENV_FILE.exists():
        # utf-8-sig strips a PowerShell-written UTF-8 BOM so SSH_HOST is found
        load_dotenv(dotenv_path=_ENV_FILE, encoding="utf-8-sig", override=True)
    else:
        load_dotenv(override=True)


@dataclass
class SSHServiceConfig:
    ssh_host: str
    ssh_identity_file: str
    ssh_working_dir: str = "/tmp"
    ssh_port: int = 22
    allow_unknown_hosts: bool = True
    service_name: str = "billing-api.service"
    log_file_path: str = "/var/log/billing-api/application.log"
    reports_dir: str = str(_CONFIG_DIR / "reports")
    summary_output_path: str = str(_CONFIG_DIR / "reports" / "healing-summary.json")
    restart_cooldown_seconds: int = 300
    max_retry_attempts: int = 3
    startup_timeout_seconds: int = 120
    api_host: str = "0.0.0.0"
    api_port: int = 8000


def load_config() -> SSHServiceConfig:
    _load_env()
    reports_dir = os.getenv("REPORTS_DIR", str(_CONFIG_DIR / "reports"))
    return SSHServiceConfig(
        ssh_host=os.getenv("SSH_HOST", "ops-agent@127.0.0.1"),
        ssh_identity_file=os.getenv(
            "SSH_IDENTITY_FILE",
            str(Path.home() / ".ssh" / "id_ed25519"),
        ),
        ssh_working_dir=os.getenv("SSH_WORKING_DIR", "/tmp"),
        ssh_port=int(os.getenv("SSH_PORT", "22")),
        allow_unknown_hosts=os.getenv("SSH_ALLOW_UNKNOWN_HOSTS", "true").lower()
        in ("1", "true", "yes"),
        service_name=os.getenv("SERVICE_NAME", "billing-api.service"),
        log_file_path=os.getenv(
            "LOG_FILE_PATH", "/var/log/billing-api/application.log"
        ),
        reports_dir=reports_dir,
        summary_output_path=os.getenv(
            "SUMMARY_OUTPUT_PATH",
            str(Path(reports_dir) / "healing-summary.json"),
        ),
        restart_cooldown_seconds=int(os.getenv("RESTART_COOLDOWN_SECONDS", "300")),
        max_retry_attempts=int(os.getenv("MAX_RETRY_ATTEMPTS", "3")),
        startup_timeout_seconds=int(os.getenv("STARTUP_TIMEOUT_SECONDS", "120")),
        api_host=os.getenv("API_HOST", "0.0.0.0"),
        api_port=int(os.getenv("API_PORT", "8000")),
    )
