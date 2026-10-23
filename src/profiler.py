# Measurement tools. Not part of the demo

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time
import sqlite3
from datetime import datetime, timedelta
from src.database import MetricsDB
from src.config import DATABASE_PATH

def profile_queries():
    """Measure query performance."""
    db = MetricsDB(DATABASE_PATH)
    
    print("\n=== QUERY PERFORMANCE PROFILING ===\n")
    
    # Test 1: Range query (most common)
    start = (datetime.now() - timedelta(days=7)).isoformat()
    end = datetime.now().isoformat()
    
    queries = [
        ("get_metrics (7 days)", lambda: db.get_metrics("latency_p95", start, end)),
        ("get_latest", lambda: db.get_latest("latency_p95")),
        ("get_all_at_time", lambda: db.get_all_at_time(datetime.now().isoformat())),
    ]
    
    for name, query_func in queries:
        times = []
        for _ in range(100):  # Run 100 times
            t0 = time.time()
            result = query_func()
            t1 = time.time()
            times.append((t1 - t0) * 1000)  # Convert to ms
        
        avg = sum(times) / len(times)
        min_t = min(times)
        max_t = max(times)
        
        print(f"{name}:")
        print(f"  Avg: {avg:.2f}ms, Min: {min_t:.2f}ms, Max: {max_t:.2f}ms")
        
        if avg > 100:
            print(f"  ⚠️  SLOW! Target <100ms")
        else:
            print(f"  ✓ Good")
        print()
    
    db.close()

if __name__ == "__main__":
    profile_queries()
