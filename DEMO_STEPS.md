Run these from **PowerShell** in order.

### 1. One-shot WSL + key + `.env` setup

```powershell
cd D:\Flytxt\CCAD\ssh-service-demo
Set-ExecutionPolicy -Scope Process Bypass
.\Setup-WslDemo.ps1
```

This will:
- create an SSH key if missing
- put your public key into Ubuntu WSL
- enable systemd / install OpenSSH / create `billing-api.service`
- write `.env` with your WSL user + IP

If the script says to restart WSL:

```powershell
wsl --shutdown
wsl -d Ubuntu
# then re-run Setup-WslDemo.ps1
```

### 2. Test SSH from PowerShell

```powershell
ssh -i $env:USERPROFILE\.ssh\id_ed25519 (Get-Content .env | Select-String '^SSH_HOST=').ToString().Split('=')[1]
```

Or manually:

```powershell
wsl -d Ubuntu hostname -I
ssh youruser@YOUR_WSL_IP
```

### 3. Install and run the agent (Windows)

```powershell
cd D:\Flytxt\CCAD\ssh-service-demo
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python self_healing_agent.py
```

### 4. Demo trigger (API + UI)

```powershell
# Terminal A — start API
cd D:\Flytxt\CCAD\ssh-service-demo
.\.venv\Scripts\Activate.ps1
python api_server.py

# Terminal B / MobaXterm — stop service
wsl -d Ubuntu -e bash -lc "sudo -n systemctl stop billing-api.service"

# Postman — POST http://localhost:8000/trigger/heal
# Browser — http://localhost:8000/  (click report for details)
```

See `DEMO_SHOWCASE.md` for the full MobaXterm + Postman walkthrough.

---

**Note:** WSL IP can change after `wsl --shutdown`. Re-run `.\Setup-WslDemo.ps1` (or update `SSH_HOST` in `.env`) if SSH stops connecting.