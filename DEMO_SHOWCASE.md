# Demo showcase — MobaXterm + Postman + Reports UI

## Start the API (Windows PowerShell)

```powershell
cd D:\Flytxt\CCAD\ssh-service-demo
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python api_server.py
```

Open:
- Reports list: http://localhost:8000/
- Health: http://localhost:8000/health

Import `postman_collection.json` into Postman.

## Live demo flow

### 1. MobaXterm — show service healthy, then stop it

SSH to WSL (`user@WSL_IP`), then:

```bash
systemctl status billing-api.service --no-pager
sudo -n systemctl stop billing-api.service
systemctl is-active billing-api.service
```

### 2. Postman — trigger heal

`POST http://localhost:8000/trigger/heal`

```json
{
  "alert": "ServiceProcessDown",
  "service_name": "billing-api.service",
  "severity": "critical",
  "host": "wsl-ubuntu",
  "message": "billing-api.service inactive / failed"
}
```

Response includes `report_id` and `report_url`.

### 3. Browser — open report

Go to http://localhost:8000/ and click the new report, or open `/reports/<report_id>` directly.

### 4. MobaXterm — confirm recovered

```bash
systemctl status billing-api.service --no-pager
curl -s http://localhost:8080/health
```

## Notes

- Each heal writes a timestamped JSON under `reports/` plus updates `healing-summary.json` as “latest”.
- CLI still works: `python self_healing_agent.py`
