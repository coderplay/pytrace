"""Example PyTrace script."""

import pytrace

# Global data structures
latencies = []
counts = {}

@function_entry("queue.Queue.put")
def on_entry(args):
    ctx["start"] = now()

@function_return("queue.Queue.put")
def on_return(retval):
    duration = (now() - ctx["start"]) * 1000
    latencies.append(duration)
    
    if "count" not in counts:
        counts["count"] = 0
    counts["count"] += 1

@timer(5000)
def report():
    print("=== Summary ===")
    print("Count:", count(latencies))
    if latencies:
        print("Avg latency:", avg(latencies), "ms")
    print("Total calls:", counts.get("count", 0))

