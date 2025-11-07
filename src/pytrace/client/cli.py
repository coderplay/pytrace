"""CLI tool for PyTrace."""

import sys
import socket
import struct
import json
import argparse
from pathlib import Path
from typing import Optional, Dict

from pytrace.client.validator import validate_script, ValidationError
from pytrace.attach.injector import attach_or_connect, check_server_exists


DEFAULT_PORT = 5678
DEFAULT_HOST = 'localhost'


def send_message(sock: socket.socket, message: Dict) -> Optional[Dict]:
    """Send a message and receive response."""
    try:
        # Send message
        data = json.dumps(message).encode('utf-8')
        length = struct.pack('>I', len(data))
        sock.sendall(length + data)
        
        # Receive response
        length_bytes = sock.recv(4)
        if not length_bytes or len(length_bytes) < 4:
            return None
        
        length = struct.unpack('>I', length_bytes)[0]
        
        data = b''
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                return None
            data += chunk
        
        return json.loads(data.decode('utf-8'))
    except Exception as e:
        print(f"Error communicating with agent: {e}", file=sys.stderr)
        return None


def handle_trace_events(sock: socket.socket):
    """Handle incoming trace events."""
    try:
        while True:
            # Check for incoming events
            sock.settimeout(0.1)  # Non-blocking
            try:
                length_bytes = sock.recv(4)
                if not length_bytes or len(length_bytes) < 4:
                    break
                
                length = struct.unpack('>I', length_bytes)[0]
                
                data = b''
                while len(data) < length:
                    chunk = sock.recv(length - len(data))
                    if not chunk:
                        break
                    data += chunk
                
                if len(data) >= length:
                    event = json.loads(data.decode('utf-8'))
                    if event.get('type') == 'trace_event':
                        if event.get('event_type') == 'print':
                            print(event.get('data', ''))
            except socket.timeout:
                # No data available, continue
                continue
            except Exception:
                break
    except KeyboardInterrupt:
        pass


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='PyTrace - Dynamic tracing tool for Python programs',
        prog='pytrace'
    )
    parser.add_argument('pid', type=int, help='Target process ID')
    parser.add_argument('script', type=str, help='Path to PyTrace script file')
    parser.add_argument('args', nargs='*', help='Arguments to pass to script')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT,
                       help=f'Socket server port (default: {DEFAULT_PORT})')
    parser.add_argument('--host', type=str, default=DEFAULT_HOST,
                       help=f'Socket server host (default: {DEFAULT_HOST})')
    parser.add_argument('--log-level', type=str, default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Log level for agent in target process (default: INFO)')
    
    args = parser.parse_args()
    
    # Read script file
    script_path = Path(args.script)
    if not script_path.exists():
        print(f"Error: Script file not found: {args.script}", file=sys.stderr)
        sys.exit(1)
    
    try:
        script_content = script_path.read_text()
    except Exception as e:
        print(f"Error reading script file: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Validate script
    try:
        is_valid, errors, handlers = validate_script(script_content)
        if not is_valid:
            print("Script validation failed:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            sys.exit(1)
    except ValidationError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error validating script: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Attach to process or connect to existing server
    print(f"Connecting to process {args.pid}...", file=sys.stderr)
    
    try:
        # Check if server exists, if not attach
        if not check_server_exists(args.port, args.host):
            print(f"Attaching to process {args.pid}...", file=sys.stderr)
            attach_or_connect(args.pid, args.port, args.host, log_level=args.log_level)
            
            # Wait a bit for server to start
            import time
            time.sleep(0.5)
        else:
            print("Found existing agent, connecting...", file=sys.stderr)
    except Exception as e:
        print(f"Error attaching to process: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Connect to server
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((args.host, args.port))
    except Exception as e:
        print(f"Error connecting to agent: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Send trace request
    print("Sending trace request...", file=sys.stderr)
    message = {
        'type': 'trace_request',
        'script_content': script_content,
        'args': args.args
    }
    
    response = send_message(sock, message)
    
    if not response:
        print("Error: No response from agent", file=sys.stderr)
        sock.close()
        sys.exit(1)
    
    if response.get('type') == 'trace_response':
        if 'error' in response:
            print(f"Error: {response['error']}", file=sys.stderr)
            sock.close()
            sys.exit(1)
        else:
            session_id = response.get('session_id')
            print(f"Tracing started (session: {session_id})", file=sys.stderr)
            print("---", file=sys.stderr)
            
            # Handle trace events
            try:
                handle_trace_events(sock)
            except KeyboardInterrupt:
                print("\nStopping trace...", file=sys.stderr)
                # Send exit request
                exit_message = {
                    'type': 'exit_request',
                    'session_id': session_id
                }
                send_message(sock, exit_message)
            finally:
                sock.close()
    else:
        print(f"Unexpected response: {response}", file=sys.stderr)
        sock.close()
        sys.exit(1)


if __name__ == '__main__':
    main()

