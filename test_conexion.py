import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from query_builder import _billing_project, _get_credentials
from google.cloud import bigquery

proj = _billing_project()
print("Billing project:", proj, flush=True)
creds = _get_credentials()
client = bigquery.Client(project=proj, credentials=creds)
job = client.query("SELECT 'OK' AS test")
rows = list(job.result())
print("BQ test:", rows[0]["test"], flush=True)
print("LISTO - conexion OK", flush=True)
