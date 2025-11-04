"""Built-in utility functions for PyTrace scripts."""

import time
from typing import Any, Iterable, List, Dict


def count(iterable: Iterable[Any]) -> int:
    """Count the number of items in an iterable."""
    return len(list(iterable))


def avg(iterable: Iterable[float]) -> float:
    """Calculate the average of numeric values in an iterable."""
    values = list(iterable)
    if not values:
        return 0.0
    return sum(values) / len(values)


def histo(data: List[float], buckets: List[float], ascii: bool = False) -> Dict[str, int]:
    """
    Generate a histogram of data values using specified buckets.
    
    Args:
        data: List of numeric values
        buckets: List of bucket boundaries (e.g., [0, 10, 50, 100])
        ascii: If True, print ASCII representation
    
    Returns:
        Dictionary mapping bucket ranges to counts
    """
    if not buckets:
        return {}
    
    # Sort buckets
    sorted_buckets = sorted(buckets)
    bucket_counts = {}
    
    # Initialize buckets
    for i in range(len(sorted_buckets) - 1):
        bucket_key = f"{sorted_buckets[i]}-{sorted_buckets[i+1]}"
        bucket_counts[bucket_key] = 0
    
    # Add overflow bucket
    bucket_counts[f">{sorted_buckets[-1]}"] = 0
    
    # Count values in buckets
    for value in data:
        placed = False
        for i in range(len(sorted_buckets) - 1):
            if sorted_buckets[i] <= value < sorted_buckets[i+1]:
                bucket_key = f"{sorted_buckets[i]}-{sorted_buckets[i+1]}"
                bucket_counts[bucket_key] += 1
                placed = True
                break
        if not placed:
            bucket_counts[f">{sorted_buckets[-1]}"] += 1
    
    if ascii:
        # Print ASCII histogram
        max_count = max(bucket_counts.values()) if bucket_counts else 1
        bar_length = 50
        
        for bucket, count_val in sorted(bucket_counts.items()):
            bar = '#' * int((count_val / max_count) * bar_length) if max_count > 0 else ''
            print(f"  {bucket:15} {count_val:6} {bar}")
    
    return bucket_counts


def topk(mapping: Dict[Any, float], k: int = 10) -> List[tuple]:
    """
    Get the top k items from a mapping by value.
    
    Args:
        mapping: Dictionary to get top items from
        k: Number of top items to return
    
    Returns:
        List of (key, value) tuples sorted by value (descending)
    """
    if not mapping:
        return []
    
    sorted_items = sorted(mapping.items(), key=lambda x: x[1], reverse=True)
    return sorted_items[:k]


def print(*args, **kwargs):
    """Safe print function that redirects output to trace events."""
    # This will be overridden in the execution environment
    # to send output to the client
    import builtins
    builtins.print(*args, **kwargs)


def now() -> float:
    """Get current timestamp in seconds since epoch."""
    return time.time()

