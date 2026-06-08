import json
import random
from datetime import datetime, timedelta, timezone
from api.db.database import db_manager
from api.models.eval_types import Route

def seed_metrics():
    print("Seeding review_decisions table in DuckDB...")
    
    # 1. Ensure table exists
    db_manager.execute("""
        CREATE TABLE IF NOT EXISTS review_decisions (
            decision_id VARCHAR PRIMARY KEY,
            route VARCHAR,
            confidence DOUBLE,
            human_agreed BOOLEAN,
            reviewed_at TIMESTAMP,
            triggers_fired VARCHAR,
            is_valid BOOLEAN,
            window_tag VARCHAR
        )
    """)

    # 2. Generate synthetic data
    # 500 records to fill the window
    records = []
    now = datetime.now(timezone.utc)
    
    # Target distribution: 70% AUTO, 20% SAMPLED_REVIEW, 10% ESCALATE
    # Agreement rate for AUTO: ~94% (just below the 95% threshold)
    
    for i in range(500):
        decision_id = f"dec_{i:04d}"
        reviewed_at = now - timedelta(minutes=i*10) # Spread over a few days
        
        rand = random.random()
        if rand < 0.70:
            route = Route.AUTO
            confidence = random.uniform(0.90, 1.0)
            # 94% agreement rate
            human_agreed = random.random() < 0.94
            triggers = []
        elif rand < 0.90:
            route = Route.SAMPLED_REVIEW
            confidence = random.uniform(0.70, 0.89)
            human_agreed = random.random() < 0.80
            triggers = []
        else:
            route = Route.ESCALATE
            confidence = random.uniform(0.0, 0.69)
            human_agreed = None # Escalated might not have human agreement yet
            
            # Add some unrecognized concepts to escalation
            if random.random() < 0.3:
                triggers = ["UNRECOGNIZED_CONCEPT"]
            else:
                triggers = ["IDENTITY_VIOLATION"]
        
        # is_valid is usually what the validator thought (before human review)
        is_valid = random.random() < 0.85

        records.append((
            decision_id,
            route.value,
            confidence,
            human_agreed,
            reviewed_at,
            json.dumps(triggers),
            is_valid,
            "seed_batch_01"
        ))

    # 3. Insert into DB
    conn = db_manager.get_connection()
    with db_manager.lock():
        # Clear existing seeds if any
        conn.execute("DELETE FROM review_decisions WHERE window_tag = 'seed_batch_01'")
        
        conn.executemany("""
            INSERT INTO review_decisions (
                decision_id, route, confidence, human_agreed, reviewed_at, triggers_fired, is_valid, window_tag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, records)

    print(f"Successfully seeded {len(records)} records.")

if __name__ == "__main__":
    seed_metrics()
