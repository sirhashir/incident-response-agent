import json

def fetch_logs(service: str) -> list[dict]:
    path = f"fixtures/{service}_logs.json"
    with open(path) as f:
        return json.load(f)
    
if __name__ == "__main__":
    result = fetch_logs("checkout")
    print(result)