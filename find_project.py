"""Encuentra el proyecto donde el usuario puede crear jobs BQ."""
import subprocess
import google.oauth2.credentials
from google.cloud import bigquery

def get_token():
    r = subprocess.run(["gcloud", "auth", "print-access-token"],
                       capture_output=True, text=True, timeout=15)
    return [l.strip() for l in r.stdout.splitlines() if l.strip()][-1]

CANDIDATOS = [
    "wmt-edw-sandbox",
    "wmt-edw-dev",
    "wmt-edw-prod",
    "wmt-apex-gemini-enterprise",
]

token = get_token()
creds = google.oauth2.credentials.Credentials(token=token)

for proj in CANDIDATOS:
    try:
        client = bigquery.Client(project=proj, credentials=creds)
        job = client.query("SELECT 1 AS test", timeout=15)
        list(job.result())
        print(f"OK -> {proj}")
    except Exception as e:
        msg = str(e)[:120].replace("\n", " ")
        print(f"FAIL [{proj}]: {msg}")
