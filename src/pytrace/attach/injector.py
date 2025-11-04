"""Process attachment mechanism using pydevd."""

import os
import sys
from typing import Optional

import pydevd
from pydevd_attach_to_process import add_code_to_python_process

def attach_to_process(pid: int, port: int = 5678, host: str = 'localhost') -> bool:
    """
    Attach to a running Python process and inject the PyTrace agent.
    
    Args:
        pid: Process ID of target Python process
        port: Port for socket server
        host: Host for socket server
    
    Returns:
        True if attachment successful, False otherwise
    """
    if pydevd is None or add_code_to_python_process is None:
        raise ImportError("pydevd is required for process attachment. Install it with: pip install pydevd")
    
    try:
        # Get the path to pytrace package
        import pytrace
        pytrace_path = os.path.dirname(os.path.dirname(pytrace.__file__))
        print(f"PyTrace path: {pytrace_path}")
        assert os.path.exists(pytrace_path), f"PyTrace path {pytrace_path} does not exist"
        
        # Code to inject into target process
        # Encode entire code block as byte array, then decode and exec() it
        # This allows multi-line code with proper function definitions
        # Since the entire code is encoded, we can use repr() and direct values
        code_to_execute = f"""
import sys
import threading

pytrace_path = {repr(pytrace_path)}
sys.path.insert(0, pytrace_path)

from pytrace.agent.socket_server import start_server
del sys.path[0]

def start_pytrace_server():
    try:
        server = start_server(port={port}, host={repr(host)})
    except Exception as e:
        import traceback
        traceback.print_exc()
server_thread = threading.Thread(target=start_pytrace_server, daemon=True)
server_thread.start()
"""

        encode_string = lambda s: list(bytearray(s.encode("utf-8"))) if s is not None else None
        # Encode the entire code block
        encoded_code = encode_string(code_to_execute)
        
        # Build injection code: decode and exec
        injection_code = (
            f"import codecs;"
            f"decode = lambda s: codecs.utf_8_decode(bytearray(s))[0] if s is not None else None;"
            f"exec(decode({encoded_code}));"
        )
        
        # Verify code doesn't contain forbidden characters (pydevd requirement)
        forbidden_chars = {'"', "'", "\r", "\n"}
        found_chars = forbidden_chars & set(injection_code)
        if found_chars:
            raise ValueError(
                f"Injected code should not contain any single quotes, double quotes, or newlines. "
                f"Found: {found_chars}"
            )
        
        # Use pydevd attach mechanism to inject code
        add_code_to_python_process.run_python_code(
            pid,
            python_code=injection_code,
            connect_debugger_tracing=False,
            show_debug_info=0,
        )
        
        return True
    except Exception as e:
        raise RuntimeError(f"Failed to attach to process {pid}: {e}")


def check_server_exists(port: int = 5678, host: str = 'localhost', timeout: float = 1.0) -> bool:
    """
    Check if PyTrace server is already running in target process.
    
    Args:
        port: Port to check
        host: Host to check
        timeout: Connection timeout in seconds
    
    Returns:
        True if server exists and is accessible, False otherwise
    """
    import socket
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def attach_or_connect(pid: int, port: int = 5678, host: str = 'localhost') -> bool:
    """
    Attach to process if server doesn't exist, otherwise just connect.
    
    Args:
        pid: Process ID
        port: Port for socket server
        host: Host for socket server
    
    Returns:
        True if server is available (either existed or was created)
    """
    # Check if server already exists
    if check_server_exists(port, host):
        return True
    
    # Attach to process
    return attach_to_process(pid, port, host)
