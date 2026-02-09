# SCRS-1913 Test Service

This is a test Flask application to verify the Threat Protection initialization behavior documented in SCRS-1913.

## Purpose

Test whether Remote Configuration can enable Threat Protection (blocking) when `DD_APPSEC_ENABLED` is not set at startup.

## Setup

### 1. Create .env File and Add Your API Key

```bash
cd test-service
cp config.template .env
```

Then edit `.env` and replace `your_api_key_here` with your actual Datadog API key:

```bash
DD_API_KEY=your_actual_api_key_here
```

### 2. Install Dependencies

```bash
cd test-service
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Test Scenarios

### Scenario 1: Without DD_APPSEC_ENABLED (Reproduces SCRS-1913)

**Expected Result:** Threat Detection works, but Threat Protection shows "Monitoring Only"

1. Make sure `DD_APPSEC_ENABLED` is **commented out** in `.env`:
   ```bash
   # DD_APPSEC_ENABLED=true
   ```

2. Start the service:
   ```bash
   source venv/bin/activate
   ddtrace-run python app.py
   ```

3. Look for `asm_enabled: False` in startup logs

4. Generate traffic:
   ```bash
   curl http://localhost:8080/
   curl http://localhost:8080/test?input=../../etc/passwd
   curl -A "Nessus" http://localhost:8080/admin
   ```

5. Check Datadog UI:
   - Go to Security → App & API Protection → Services
   - Find `scrs-1913-test` service
   - **Expected:** Threat Protection shows "Monitoring Only"

### Scenario 2: With DD_APPSEC_ENABLED (The Fix)

**Expected Result:** Threat Protection becomes "Ready to Block" or "Active"

1. **Uncomment** `DD_APPSEC_ENABLED` in `.env`:
   ```bash
   DD_APPSEC_ENABLED=true
   ```

2. **Restart the service** (Ctrl+C, then):
   ```bash
   ddtrace-run python app.py
   ```

3. Look for `asm_enabled: True` in startup logs

4. Generate traffic again:
   ```bash
   curl http://localhost:8080/
   curl http://localhost:8080/test?input=../../etc/passwd
   curl -A "Nessus" http://localhost:8080/admin
   ```

5. Check Datadog UI:
   - **Expected:** Threat Protection shows "Ready to Block" or "Active"

## Verification Steps

### Check Startup Logs

Look for these lines in the tracer startup logs:

**Without DD_APPSEC_ENABLED:**
```
'asm_enabled': False
'remote_config_enabled': True
```

**With DD_APPSEC_ENABLED:**
```
'asm_enabled': True
'remote_config_enabled': True
```

### Check Datadog UI

1. **Services Page:** Security → App & API Protection → Configuration → Services
   - Search for `scrs-1913-test`
   - Check Threat Protection status

2. **Capabilities Tab:**
   - Without flag: No blocking capabilities registered
   - With flag: Should show `ASM_IP_BLOCKING`, `ASM_USER_BLOCKING`, `ASM_REQUEST_BLOCKING`

3. **Traces Explorer:** Security → App & API Protection → Traces
   - Should see security traces in both scenarios
   - Blocking only available in Scenario 2

## Cleanup

```bash
deactivate  # Exit virtualenv
rm -rf venv/
```

## Notes

- This test reproduces the exact issue from SCRS-1913
- Remote Config successfully enables API Security features in both scenarios
- But blocking engine initialization requires `DD_APPSEC_ENABLED=true` at startup
- A full service restart is required after adding the flag

