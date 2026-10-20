import concurrent.futures
import time
import requests
from datetime import datetime, timedelta

def test_load(base_url="http://localhost:8000", num_requests=10000):
    """Simulate 10K requests/min."""
    
    print(f"\n=== LOAD TEST: {num_requests} requests ===\n")
    
    endpoints = [
        "/health",
        "/metrics?name=latency_p95&start=2026-10-01T00:00:00&end=2026-10-08T23:59:59",
        "/metrics/latest?name=cpu_percent",
        "/anomalies?days=7"
    ]
    
    results = {
        "success": 0,
        "failed": 0,
        "times": []
    }
    
    def make_request(endpoint):
        try:
            t0 = time.time()
            resp = requests.get(f"{base_url}{endpoint}", timeout=5)
            t1 = time.time()
            
            if resp.status_code == 200:
                results["success"] += 1
                results["times"].append((t1 - t0) * 1000)
                return True
            else:
                results["failed"] += 1
                return False
        except Exception as e:
            results["failed"] += 1
            print(f"Error: {e}")
            return False
    
    # Send requests in parallel (simulates concurrent users)
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        futures = []
        for i in range(num_requests):
            endpoint = endpoints[i % len(endpoints)]
            futures.append(executor.submit(make_request, endpoint))
        
        # Wait for all
        concurrent.futures.wait(futures)
    
    # Print results
    print(f"Success: {results['success']}/{num_requests}")
    print(f"Failed: {results['failed']}/{num_requests}")
    
    if results["times"]:
        avg_time = sum(results["times"]) / len(results["times"])
        min_time = min(results["times"])
        max_time = max(results["times"])
        
        print(f"\nResponse times:")
        print(f"  Avg: {avg_time:.2f}ms")
        print(f"  Min: {min_time:.2f}ms")
        print(f"  Max: {max_time:.2f}ms")
        
        if avg_time > 100:
            print(f"  ⚠️  SLOW! Should be <100ms")
        else:
            print(f"  ✓ Good")
    
    throughput = num_requests / 60  # requests per second
    print(f"\nThroughput: {throughput:.0f} req/s ({num_requests} in 1 min)")

if __name__ == "__main__":
    test_load(num_requests=10000)
