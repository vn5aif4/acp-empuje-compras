"""Quick BQ connectivity test — no bloat."""
import subprocess
import sys

import google.oauth2.credentials
from google.cloud import bigquery

print("Step 1: getting gcloud token...", flush=True)
GCLOUD = r"C:\Users\vn5aif4\AppData\Local\Google\CloudSDK\google-cloud-sdk\bin\gcloud.cmd"
result = subprocess.run(
    [GCLOUD, "auth", "print-access-token"],
    capture_output=True, text=True, timeout=15, shell=True
)
lineas = [l.strip() for l in result.stdout.splitlines() if l.strip()]
token = lineas[-1]
print(f"Token OK (starts with: {token[:20]}...)", flush=True)

print("Step 2: creating BQ client...", flush=True)
creds = google.oauth2.credentials.Credentials(token=token)
client = bigquery.Client(project="wmt-edw-prod", credentials=creds)

print("Step 3: running test query...", flush=True)
# Try multiple projects
for proj in ['wmt-edw-dev', 'wmt-9ca45f77fc0cfa9cafcba7a82a', 'wmt-1257d458107910dad54c01f5c8']:
    try:
        client = bigquery.Client(project=proj, credentials=creds)
        job = client.query(
            "SELECT COUNT(*) AS n FROM `wmt-edw-sandbox.DMP.DRV_ACP_DMP` WHERE STATUS = 'A' LIMIT 1"
        )
        rows = list(job.result())
        print(f"SUCCESS with project={proj}! Filas: {rows[0]['n']}", flush=True)
        break
    except Exception as e:
        print(f"FAIL {proj}: {str(e)[:120]}", flush=True)
