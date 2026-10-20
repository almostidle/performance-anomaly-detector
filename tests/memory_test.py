import psutil
import time
import requests
from datetime import datetime, timedelta

def test_memory_leak(base_url="http://localhost:8000", duration_seconds=300):
    """Run for 5 min, check memory usage."""
    
    print(f"\n=== MEMORY LEAK TEST: {duration_seconds}s ===\n")
    
    process = psutil.Process()
    measurements = []
    
    endpoint = "/metrics?name=latency_p95&start=2026-10-01T00:00:00&end=2026-10-08T23:59:59"
    
    start_time = time.time()
    request_count = 0
    
    while time.time() - start_time < duration_seconds:
        try:
            # Make request
            resp = requests.get(f"{base_url}{endpoint}", timeout=5)
            request_count += 1
            
            # Every 30 sec, measure memory
            if request_count % 100 == 0:
                mem = process.memory_info().rss / (1024 * 1024)  # MB
                elapsed = time.time() - start_time
                measurements.append((elapsed, mem))
                print(f"t={elapsed:.0f}s: {request_count} requests, Memory={mem:.2f}MB")
        
        except Exception as e:
            print(f"Error: {e}")
    
    # Check if memory grew linearly (leak) or stayed flat (ok)
    if len(measurements) > 1:
        start_mem = measurements[0][1]
        end_mem = measurements[-1][1]
        growth = end_mem - start_mem
        
        print(f"\nMemory growth: {growth:.2f}MB over {duration_seconds}s")
        
        if growth > 100:
            print(f"  ⚠️  LEAK! Memory growing too fast")
        else:
            print(f"  ✓ OK")

if __name__ == "__main__":
    test_memory_leak(duration_seconds=300)
