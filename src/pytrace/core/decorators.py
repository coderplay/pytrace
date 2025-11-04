"""Decorators for PyTrace scripts."""

import threading
from typing import Dict, Callable, Any, Optional
from collections import defaultdict


# Global registry for decorators
# This will be populated when scripts are executed
_handlers: Dict[str, Dict[str, list]] = {
    'function_entry': defaultdict(list),
    'function_return': defaultdict(list),
    'on_exception': defaultdict(list),
    'timer': []
}

# Thread-local context for per-invocation data
_context = threading.local()


def get_context() -> Dict[str, Any]:
    """Get thread-local context dictionary."""
    if not hasattr(_context, 'ctx'):
        _context.ctx = {}
    return _context.ctx


def clear_context():
    """Clear thread-local context."""
    if hasattr(_context, 'ctx'):
        _context.ctx.clear()


def function_entry(pattern: str):
    """
    Decorator to register a function entry handler.
    
    Args:
        pattern: Function pattern to match (e.g., "http.handle_request")
    
    Example:
        @function_entry("http.handle_request")
        def on_entry(args):
            ctx["start"] = now()
    """
    def decorator(func: Callable):
        _handlers['function_entry'][pattern].append(func)
        return func
    return decorator


def function_return(pattern: str):
    """
    Decorator to register a function return handler.
    
    Args:
        pattern: Function pattern to match
    
    Example:
        @function_return("http.handle_request")
        def on_return(retval):
            duration = now() - ctx["start"]
            latencies.append(duration)
    """
    def decorator(func: Callable):
        _handlers['function_return'][pattern].append(func)
        return func
    return decorator


def on_exception(pattern: str):
    """
    Decorator to register an exception handler.
    
    Args:
        pattern: Function pattern to match
    
    Example:
        @on_exception("http.handle_request")
        def on_exc(exc):
            errors[type(exc).__name__] = errors.get(type(exc).__name__, 0) + 1
    """
    def decorator(func: Callable):
        _handlers['on_exception'][pattern].append(func)
        return func
    return decorator


def timer(interval_ms: int):
    """
    Decorator to register a timer callback.
    
    Args:
        interval_ms: Interval in milliseconds
    
    Example:
        @timer(5000)  # Every 5 seconds
        def report():
            print("Summary:", count(latencies))
    """
    def decorator(func: Callable):
        _handlers['timer'].append({
            'function': func,
            'interval_ms': interval_ms
        })
        return func
    return decorator


def get_handlers() -> Dict[str, Dict[str, list]]:
    """Get the current handler registry."""
    return _handlers


def reset_handlers():
    """Reset the handler registry (for testing or cleanup)."""
    global _handlers
    _handlers = {
        'function_entry': defaultdict(list),
        'function_return': defaultdict(list),
        'on_exception': defaultdict(list),
        'timer': []
    }

