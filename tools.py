import json

def fetch_logs(service: str) -> list[dict]:
    """Return recent log lines for a service."""
    path = f"fixtures/{service}_logs.json"
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return [{"time": "N/A", "level": "INFO", "message": f"No logs found for service '{service}'"}]


def get_deploy_history(service: str) -> list[dict]:
    """Return recent deploys across all services (agent filters as needed)."""
    with open("fixtures/deploys.json") as f:
        deploys = json.load(f)
    return [d for d in deploys if d["service"] == service] or deploys