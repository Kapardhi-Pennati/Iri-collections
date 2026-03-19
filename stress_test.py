import concurrent.futures
import time
import os

# Remove SSL logging variable that causes Windows python bug on this environment
os.environ.pop('SSLKEYLOGFILE', None)

import requests

API_URL = "http://localhost:8000/api/store/products/"

def make_request(i):
    try:
        response = requests.get(API_URL)
        return response.status_code
    except Exception as e:
        return str(e)

if __name__ == "__main__":
    print(f"Starting stress test on {API_URL}...")
    print("Testing DDoS protection (Rate Limiting). Sending 75 concurrent requests.")
    print("Note: Throttling limit is set to 60 requests per minute for anonymous users.")
    
    start_time = time.time()
    
    # Send 75 requests using a thread pool
    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
        futures = [executor.submit(make_request, i) for i in range(75)]
        
        status_codes = []
        for future in concurrent.futures.as_completed(futures):
            status_codes.append(future.result())
            
    end_time = time.time()
    
    success_count = sum(1 for code in status_codes if code == 200)
    throttled_count = sum(1 for code in status_codes if code == 429)
    other_errors = len(status_codes) - success_count - throttled_count
    
    print(f"\nResults completed in {end_time - start_time:.2f} seconds:")
    print(f"Total Requests: {len(status_codes)}")
    print(f"Successful (200 OK): {success_count}")
    print(f"Throttled blocked (429 Too Many Requests): {throttled_count}")
    if other_errors > 0:
        print(f"Other Errors: {other_errors}")
        for code in status_codes:
            if code not in (200, 429):
                print(f" - Error details: {code}")
                break

    if throttled_count > 0:
        print("\n✅ Security Check Passed: Rate limiting gracefully blocked the excess load and protected the server.")
    else:
        print("\n❌ Security Check Failed: Server failed to throttle requests.")
