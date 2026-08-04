# Self-Healing Demo

## Setup

* **Service** \- The service to monitor and restart (e.g “billing-api.service”)  
* **Target server** \- Linux server IP/hostname  
* **Credentials** \- SSH account to stop/start the service  
* **Log file location** \- Path to the service's log file (e.g “/var/log/billing-api/application.log”)  
* **Summary output path** \- Where to save the generated report (e.g “/tmp/self-healing-summary.json”)

## Demo Flow

1. **Trigger comes**  
   1. Service-down alert initiates the agent (e.g., “billing-api.service” inactive / failed)  
   2. Agent receives service name and target server details

2. **Agent connects via SSH**  
   1. Opens SSH session to the remote Linux server  
   2. Ready to run status, stop, and start commands

3. **Agent checks service status (health)**  
   1. Checks whether the service is running: \`systemctl is-active billing-api.service\`  
   2. Checks overall service health/status: “systemctl status billing-api.service \--no-pager.”  
   3. Confirms service is stopped or failed

4. **Check logs**  
   1. Reads recent service log entries from journal and app log file  
   2. Parses log file for recent error traces  
   3. Extracts last error lines with timestamps  

   **What failure logs look like (before restart):**

   ```
   Jul 21 14:02:11 dev-app-001 billing-api[4821]: FATAL: OutOfMemoryError - heap space exhausted
   Jul 21 14:02:11 dev-app-001 systemd[1]: billing-api.service: Main process exited, code=exited, status=137
   Jul 21 14:02:11 dev-app-001 systemd[1]: billing-api.service: Failed with result 'signal'.
   Jul 21 14:02:12 dev-app-001 billing-api[4821]: Application shutdown complete
   ```

   Agent uses these lines to confirm the service crashed (not just a monitoring false alarm) and to capture the failure reason for the summary.

5. **Identifies reason**  
   1. Analyzes log content for crash or exit cause (e.g. OOM kill, exit code 137)  
   2. Determines service needs a restart

6. **Stops and starts service**  
   1. Stops the service: `systemctl stop billing-api.service`  
   2. Starts the service: `systemctl start billing-api.service`  
   3. Waits briefly for startup  

   **What appears in logs when the service starts:**

   ```
   Jul 21 14:05:01 dev-app-001 systemd[1]: Starting billing-api.service - Billing API...
   Jul 21 14:05:02 dev-app-001 billing-api[5102]: Loading configuration from /opt/billing-api/config.yaml
   Jul 21 14:05:02 dev-app-001 billing-api[5102]: Connecting to database...
   Jul 21 14:05:03 dev-app-001 billing-api[5102]: Database connection established
   Jul 21 14:05:03 dev-app-001 billing-api[5102]: Server listening on 0.0.0.0:8080
   Jul 21 14:05:03 dev-app-001 billing-api[5102]: billing-api started successfully - ready to accept requests
   Jul 21 14:05:03 dev-app-001 systemd[1]: Started billing-api.service - Billing API.
   ```

   The key startup confirmation lines are **"Server listening"** and **"started successfully"** — these tell the agent the process is up and accepting work, not just that systemd launched a shell command.

7. **Verifies service is running (health)**  
   1. Confirms `systemctl is-active billing-api.service` returns `active`  
   2. Re-checks `systemctl status` — shows `Active: active (running)` with a new PID  
   3. Confirms no new errors in recent logs after the restart timestamp  

   **What healthy post-restart logs look like (confirmation):**

   ```
   Jul 21 14:05:03 dev-app-001 billing-api[5102]: billing-api started successfully - ready to accept requests
   Jul 21 14:05:04 dev-app-001 billing-api[5102]: GET /health 200 OK (2ms)
   Jul 21 14:05:05 dev-app-001 billing-api[5102]: Health check passed - all dependencies OK
   ```

   Agent treats the service as **fully recovered** when:
   - systemd reports `active (running)`   
   - startup success message appears in logs
   - health endpoint returns `200 OK` in access log (if applicable)
   - no `ERROR`, `FATAL`, or `Failed with result` lines appear after the restart time

8. **Creates summary → saves it**  
   1. Compiles report:  
      1. Failure timestamp and alert that triggered the run  
      2. Root cause from logs  
      3. Actions taken (stop / start commands)  
      4. Verification results and final service state  
      5. Writes summary to configured output path (JSON format)
