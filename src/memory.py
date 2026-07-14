import psycopg
import os
from dotenv import load_dotenv

load_dotenv()

DB_PASSWORD = os.environ["DB_PASSWORD"]
DB_CONFIG = f"dbname=incidents user=postgres password={DB_PASSWORD} host=localhost port=5434"

def save_incident(service, incident_description, hypothesis, proposed_action, approved):
    with psycopg.connect(DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO incidents (service, incident_description, hypothesis, proposed_action, approved)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (service, incident_description, hypothesis, proposed_action, approved)
            )
        conn.commit()
    print(f"Saved incident for service '{service}' to database.")

def recall_similar(service, limit=3):
    with psycopg.connect(DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT incident_description, hypothesis, proposed_action, approved
                FROM incidents
                WHERE service = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (service, limit)
            )
            rows = cur.fetchall()
    
    past=[]
    for row in rows:
        past.append({
            "incident": row[0],
            "hypothesis": row[1],
            "proposed_action": row[2],
            "approved": row[3]
        })
    
    print(f"recall_similar: found {len(past)} past incident(s) for '{service}'")
    return past

def reset_and_seed_memory(seed_incidents):
    """Clear the incidents table and insert a known fixed set. Used by evals only."""
    with psycopg.connect(DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM incidents")
            for inc in seed_incidents:
                cur.execute(
                    """
                    INSERT INTO incidents (service, incident_description, hypothesis, proposed_action, approved)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (inc["service"], inc["incident"], inc["hypothesis"], inc["proposed_action"], inc["approved"])
                )
        conn.commit()
    print(f"Seeded memory with {len(seed_incidents)} known past incidents.")

if __name__ == "__main__":
    results = recall_similar("checkout")
    for r in results:
        print(r)