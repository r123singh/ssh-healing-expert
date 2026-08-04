# SSH Self-Healing Agent — Quick Start

Run the agent on **Windows**. It SSHs into a **Linux** host (VM, cloud, or WSL2) to check, restart, and verify a systemd service.

Remote server prep is in the second half of this file. Agent setup is below.

---

## Prerequisites

- Windows 10/11 with Python 3.10+
- Network (or WSL) access to a Linux host with SSH + the demo service
- SSH private key that can log into that host
- AWS credentials / model access configured for Strands (same as `basic-demo`)

---

## 1. Install the agent

```powershell
cd D:\Flytxt\CCAD\ssh-service-demo
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 2. Configure environment

```powershell
copy .env.example .env
notepad .env
```

Set at least:

```ini
SSH_HOST=ops-agent@172.28.123.45
SSH_IDENTITY_FILE=C:\Users\YourName\.ssh\id_rsa
SSH_PORT=22
SERVICE_NAME=billing-api.service
LOG_FILE_PATH=/var/log/billing-api/application.log
SUMMARY_OUTPUT_PATH=D:\Flytxt\CCAD\ssh-service-demo\reports\healing-summary.json
```

| Variable | Meaning |
|----------|---------|
| `SSH_HOST` | `user@host` or hostname/IP of the Linux target |
| `SSH_IDENTITY_FILE` | Path to your private key on Windows |
| `SSH_PORT` | Usually `22` |
| `SERVICE_NAME` | systemd unit (e.g. `billing-api.service`) |
| `LOG_FILE_PATH` | App log on the remote host |
| `SUMMARY_OUTPUT_PATH` | Where the agent writes the JSON summary (local path) |

---

## 3. Test SSH from Windows

```powershell
ssh -i $env:USERPROFILE\.ssh\id_rsa ops-agent@172.28.123.45
```

On the remote host, confirm:

```bash
systemctl is-active billing-api.service
systemctl status billing-api.service --no-pager
```

Exit SSH when done.

---

## 4. Run the agent

```powershell
cd D:\Flytxt\CCAD\ssh-service-demo
.\.venv\Scripts\Activate.ps1
python self_healing_agent.py
```

Or override service/host:

```powershell
python self_healing_agent.py billing-api.service ops-agent@172.28.123.45
```

### What the agent does

1. Connects via SSH (`SshSandbox` / remote shell tools)
2. Checks service status (`systemctl is-active` / `status`)
3. Reads recent logs (journal + log file)
4. Stops and starts the service if down/failed
5. Verifies `active (running)` and healthy log lines
6. Writes a JSON summary to `SUMMARY_OUTPUT_PATH`

Matches the flow in `DEMO_FLOW.md`.

---

## 5. Demo trigger

On the Linux host (or via SSH):

```bash
sudo systemctl stop billing-api.service
```

Then run the agent from Windows — it should detect inactive/failed, restart, verify, and save the summary.

---

## Agent architecture (how it is wired)

```text
Windows (agent host)                    Linux (remote / WSL)
─────────────────────                   ────────────────────
self_healing_agent.py
   └─ Strands Agent
         └─ SshSandbox tools  ──SSH──►  systemctl / journalctl / logs
         └─ save_healing_summary ───►  reports\healing-summary.json (local)
```

Core idea (from project `setup.txt`):

```python
from strands import Agent
from strands.sandbox.ssh import SshSandbox

ssh_sandbox = SshSandbox(
    host="ops-agent@your-linux-host",
    identity_file=r"C:\Users\YourName\.ssh\id_rsa",
    port=22,
    allow_unknown_hosts=True,
)

agent = Agent(
    tools=ssh_sandbox.get_tools(),
    description="Ops agent that diagnoses and restarts remote systemd services.",
)
```

For production, prefer **constrained tools** (status / stop / start / read logs only) instead of open-ended shell — see `setup.txt`.

---

## Remote Linux / WSL setup (target)

### A. Real Linux server

1. OpenSSH (`sshd`) running; port reachable from Windows
2. systemd unit for the demo service (e.g. `billing-api.service`)
3. User with key auth + passwordless sudo for the few `systemctl` commands:

```text
ops-agent ALL=(root) NOPASSWD: /bin/systemctl is-active billing-api.service, /bin/systemctl status billing-api.service, /bin/systemctl stop billing-api.service, /bin/systemctl start billing-api.service, /bin/systemctl restart billing-api.service
```

4. Readable logs: `journalctl -u billing-api.service` and/or `/var/log/billing-api/application.log`

### B. WSL2 on the same Windows PC (local PoC)

1. Enable systemd in `/etc/wsl.conf`:

```ini
[boot]
systemd=true
```

Then from PowerShell: `wsl --shutdown` and reopen WSL.

2. Install and start SSH:

```bash
sudo apt update && sudo apt install -y openssh-server
sudo systemctl enable --now ssh
```

3. Create/start the demo service; add your Windows public key to `~/.ssh/authorized_keys`
4. Get WSL IP: `hostname -I` — use that in `SSH_HOST`
5. From PowerShell: `ssh <wsl-user>@<wsl-ip>`

WSL IP can change after reboot; re-check before demos.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `Permission denied (publickey)` | Fix key path in `.env`; confirm public key on remote |
| `Connection refused` | SSH not running on Linux/WSL; check port/firewall |
| `Failed to start billing-api.service` | Unit missing or bad `ExecStart`; fix unit then `daemon-reload` |
| Agent has no model / AWS error | Configure same Strands/Bedrock credentials as `basic-demo` |
| `sudo` asks for password | Add NOPASSWD sudoers rule for the specific systemctl commands |

---

## Related files

- `DEMO_FLOW.md` — demo story and expected log lines
- `self_healing_agent.py` — agent entry point
- `config.py` — loads `.env`
- `../setup.txt` — Strands SSH sandbox vs constrained production tools
