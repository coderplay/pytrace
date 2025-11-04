"""Basic tests for PyTrace."""

import pytest
from pytrace.client.validator import validate_script, ValidationError
from pytrace.core import builtins, decorators
from pytrace.agent.registry import SessionRegistry


def test_validator_allows_valid_script():
    """Test that validator accepts valid scripts."""
    script = """
import pytrace

latencies = []

@function_entry("test.func")
def on_entry(args):
    ctx["start"] = now()

@function_return("test.func")
def on_return(retval):
    latencies.append(1)
"""
    is_valid, errors, handlers = validate_script(script)
    assert is_valid
    assert len(errors) == 0


def test_validator_rejects_loops():
    """Test that validator rejects loops."""
    script = """
import pytrace

for i in range(10):
    pass
"""
    is_valid, errors, handlers = validate_script(script)
    assert not is_valid
    assert any("loop" in error.lower() for error in errors)


def test_validator_rejects_classes():
    """Test that validator rejects class definitions."""
    script = """
import pytrace

class Test:
    pass
"""
    is_valid, errors, handlers = validate_script(script)
    assert not is_valid
    assert any("class" in error.lower() for error in errors)


def test_builtins_count():
    """Test count builtin."""
    assert builtins.count([1, 2, 3]) == 3
    assert builtins.count([]) == 0


def test_builtins_avg():
    """Test avg builtin."""
    assert builtins.avg([1, 2, 3, 4]) == 2.5
    assert builtins.avg([]) == 0.0


def test_builtins_histo():
    """Test histo builtin."""
    data = [5, 15, 25, 35, 45, 55]
    buckets = [0, 10, 50, 100]
    result = builtins.histo(data, buckets)
    assert "0-10" in result
    assert "10-50" in result
    assert "50-100" in result


def test_builtins_topk():
    """Test topk builtin."""
    mapping = {"a": 10, "b": 20, "c": 5, "d": 15}
    result = builtins.topk(mapping, k=2)
    assert len(result) == 2
    assert result[0][1] >= result[1][1]  # Sorted descending


def test_registry():
    """Test session registry."""
    registry = SessionRegistry()
    
    # Register session
    session_id = registry.register("script", [], {"handlers": {}})
    assert session_id is not None
    
    # Get session
    session = registry.get(session_id)
    assert session is not None
    assert session["script_content"] == "script"
    
    # Unregister
    assert registry.unregister(session_id)
    assert registry.get(session_id) is None


def test_registry_count():
    """Test registry session count."""
    registry = SessionRegistry()
    assert registry.count() == 0
    
    registry.register("script1", [], {"handlers": {}})
    assert registry.count() == 1
    
    registry.register("script2", [], {"handlers": {}})
    assert registry.count() == 2

