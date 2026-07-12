import json
import os

FIXTURE_DIR = "fixtures"
CURRENT_INCIDENT = None

def set_incident(incident_id: str):
    """Tell the tools which incident's fixtures to read from."""
    global CURRENT_INCIDENT
    CURRENT_INCIDENT = incident_id

def fetch_logs(service: str) -> list[dict]:
    """Return recent log lines for a service."""
    path = os.path.join(FIXTURE_DIR, CURRENT_INCIDENT, "logs.json")
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return [{"time": "N/A", "level": "INFO", "message": f"No logs available for '{service}'"}]

def get_deploy_history(service: str) -> list[dict]:
    """Return recent deployments."""
    path = os.path.join(FIXTURE_DIR, CURRENT_INCIDENT, "deploys.json")
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return []