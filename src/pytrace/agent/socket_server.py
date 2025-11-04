"""Socket server for multi-client communication."""

import socket
import threading
import struct
import uuid
import logging
from typing import Optional, Dict, Callable, Union
import json

from pytrace.agent.registry import SessionRegistry
from pytrace.agent.executor import ScriptExecutor
from pytrace.agent.tracer import Tracer

# Setup logger
logger = logging.getLogger(__name__)


# Default port for PyTrace agent
DEFAULT_PORT = 5678


class SocketServer:
    """TCP socket server for PyTrace agent."""
    
    def __init__(self, port: int = DEFAULT_PORT, host: str = 'localhost'):
        """
        Initialize socket server.
        
        Args:
            port: Port to listen on
            host: Host to bind to
        """
        self.port = port
        self.host = host
        self.socket: Optional[socket.socket] = None
        self.running = False
        self.registry = SessionRegistry()
        self.tracer: Optional[Tracer] = None
        self.clients: Dict[socket.socket, threading.Thread] = {}
        self.executors: Dict[str, ScriptExecutor] = {}  # session_id -> executor
        self._lock = threading.RLock()
        
        # Start tracer
        logger.debug(f"Initializing SocketServer on {host}:{port}")
        self.tracer = Tracer(self.registry)
        self.tracer.start()
        logger.debug("Tracer started")
    
    def start(self):
        """Start the socket server."""
        with self._lock:
            if self.running:
                logger.debug("Server already running, skipping start")
                return
            
            logger.info(f"Starting socket server on {self.host}:{self.port}")
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(10)
            self.running = True
            logger.info(f"Socket server listening on {self.host}:{self.port}")
        
        # Start accepting connections
        accept_thread = threading.Thread(target=self._accept_connections, daemon=True)
        accept_thread.start()
        logger.debug("Accept thread started")
    
    def stop(self):
        """Stop the socket server."""
        with self._lock:
            if not self.running:
                logger.debug("Server not running, skipping stop")
                return
            
            logger.info("Stopping socket server")
            self.running = False
            
            # Close all client connections
            client_count = len(self.clients)
            logger.debug(f"Closing {client_count} client connections")
            for client_sock in list(self.clients.keys()):
                try:
                    client_sock.close()
                except Exception as e:
                    logger.debug(f"Error closing client socket: {e}")
            
            self.clients.clear()
            
            # Cleanup all executors
            executor_count = len(self.executors)
            logger.debug(f"Cleaning up {executor_count} executors")
            for executor in list(self.executors.values()):
                try:
                    executor.cleanup()
                except Exception as e:
                    logger.debug(f"Error cleaning up executor: {e}")
            self.executors.clear()
            
            if self.socket:
                try:
                    self.socket.close()
                    logger.debug("Server socket closed")
                except Exception as e:
                    logger.debug(f"Error closing server socket: {e}")
            
            if self.tracer:
                self.tracer.stop()
                logger.debug("Tracer stopped")
            
            logger.info("Socket server stopped")
    
    def _accept_connections(self):
        """Accept incoming connections."""
        logger.debug("Accept thread started, waiting for connections")
        while self.running:
            try:
                client_sock, addr = self.socket.accept()
                logger.info(f"New client connected from {addr[0]}:{addr[1]}")
                
                # Handle client in separate thread
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, addr),
                    daemon=True
                )
                client_thread.start()
                
                with self._lock:
                    self.clients[client_sock] = client_thread
                logger.debug(f"Client handler thread started, total clients: {len(self.clients)}")
            except Exception as e:
                if self.running:
                    logger.error(f"Error accepting connection: {e}", exc_info=True)
                    break
                else:
                    logger.debug("Server stopped, accept loop exiting")
                    break
    
    def _handle_client(self, client_sock: socket.socket, addr):
        """Handle a client connection."""
        logger.debug(f"Handling client {addr[0]}:{addr[1]}")
        try:
            while self.running:
                # Read message length (4 bytes)
                length_bytes = client_sock.recv(4)
                if not length_bytes or len(length_bytes) < 4:
                    logger.debug(f"Client {addr[0]}:{addr[1]} disconnected (no data)")
                    break
                
                length = struct.unpack('>I', length_bytes)[0]
                logger.debug(f"Received message from {addr[0]}:{addr[1]}, length: {length}")
                
                # Read message data
                data = b''
                while len(data) < length:
                    chunk = client_sock.recv(length - len(data))
                    if not chunk:
                        logger.debug(f"Client {addr[0]}:{addr[1]} disconnected during data read")
                        break
                    data += chunk
                
                if len(data) < length:
                    logger.warning(f"Incomplete message from {addr[0]}:{addr[1]}, expected {length}, got {len(data)}")
                    break
                
                # Parse and handle message
                try:
                    message = json.loads(data.decode('utf-8'))
                    logger.debug(f"Parsed message from {addr[0]}:{addr[1]}: type={message.get('type')}")
                    response = self._handle_message(message, client_sock)
                    
                    if response:
                        # Send response
                        response_data = json.dumps(response).encode('utf-8')
                        response_length = struct.pack('>I', len(response_data))
                        client_sock.sendall(response_length + response_data)
                        logger.debug(f"Sent response to {addr[0]}:{addr[1]}, length: {len(response_data)}")
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error from {addr[0]}:{addr[1]}: {e}")
                    # Send error response
                    error_response = {
                        'type': 'error',
                        'error': f'Invalid JSON: {str(e)}'
                    }
                    response_data = json.dumps(error_response).encode('utf-8')
                    response_length = struct.pack('>I', len(response_data))
                    client_sock.sendall(response_length + response_data)
                except Exception as e:
                    logger.error(f"Error handling message from {addr[0]}:{addr[1]}: {e}", exc_info=True)
                    # Send error response
                    error_response = {
                        'type': 'error',
                        'error': str(e)
                    }
                    response_data = json.dumps(error_response).encode('utf-8')
                    response_length = struct.pack('>I', len(response_data))
                    client_sock.sendall(response_length + response_data)
        except Exception as e:
            logger.error(f"Error in client handler for {addr[0]}:{addr[1]}: {e}", exc_info=True)
        finally:
            # Cleanup
            logger.debug(f"Cleaning up client connection {addr[0]}:{addr[1]}")
            try:
                client_sock.close()
            except Exception as e:
                logger.debug(f"Error closing client socket: {e}")
            
            with self._lock:
                if client_sock in self.clients:
                    del self.clients[client_sock]
            logger.info(f"Client {addr[0]}:{addr[1]} disconnected, remaining clients: {len(self.clients)}")
    
    def _handle_message(self, message: Dict, client_sock: socket.socket) -> Optional[Dict]:
        """Handle a message from client."""
        msg_type = message.get('type')
        logger.debug(f"Handling message type: {msg_type}")
        
        if msg_type == 'trace_request':
            return self._handle_trace_request(message, client_sock)
        elif msg_type == 'exit_request':
            return self._handle_exit_request(message)
        elif msg_type == 'event_request':
            return self._handle_event_request(message)
        else:
            logger.warning(f"Unknown message type: {msg_type}")
            return {'type': 'error', 'error': f'Unknown message type: {msg_type}'}
    
    def _handle_trace_request(self, message: Dict, client_sock: socket.socket) -> Dict:
        """Handle trace request."""
        try:
            script_content = message.get('script_content', '')
            args = message.get('args', [])
            script_length = len(script_content)
            logger.info(f"Received trace request: script_length={script_length}, args={args}")
            
            # Create print callback for this client
            def print_callback(text: str):
                """Send print output to client."""
                try:
                    event = {
                        'type': 'trace_event',
                        'event_type': 'print',
                        'data': text
                    }
                    event_data = json.dumps(event).encode('utf-8')
                    event_length = struct.pack('>I', len(event_data))
                    client_sock.sendall(event_length + event_data)
                except Exception as e:
                    logger.debug(f"Error sending print event: {e}")
            
            # Register session first to get session_id
            session_id = str(uuid.uuid4())
            logger.debug(f"Created session_id: {session_id}")
            
            # Create executor with session_id
            executor = ScriptExecutor(session_id, print_callback)
            logger.debug(f"Created executor for session {session_id}")
            
            # Execute script to get handlers
            logger.debug(f"Executing script for session {session_id}")
            handlers = executor.execute(script_content, args)
            logger.debug(f"Script executed, handlers registered: {list(handlers.keys())}")
            
            # Register session in registry (using internal method to set session_id)
            with self._lock:
                # Store executor first
                self.executors[session_id] = executor
                # Register session
                self.registry._sessions[session_id] = {
                    'script_content': script_content,
                    'args': args,
                    'handlers': handlers,
                    'globals': executor.globals,
                    'namespace': executor.namespace,
                    'executor': executor,  # Store executor reference for tracer
                }
            
            logger.info(f"Session {session_id} registered successfully, total sessions: {self.registry.count()}")
            return {
                'type': 'trace_response',
                'session_id': session_id
            }
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            logger.error(f"Error handling trace request: {e}", exc_info=True)
            return {
                'type': 'trace_response',
                'error': error_msg
            }
    
    def _handle_exit_request(self, message: Dict) -> Dict:
        """Handle exit request."""
        session_id = message.get('session_id', '')
        logger.debug(f"Received exit request for session: {session_id}")
        
        if session_id:
            # Cleanup executor
            with self._lock:
                if session_id in self.executors:
                    logger.debug(f"Cleaning up executor for session {session_id}")
                    executor = self.executors[session_id]
                    executor.cleanup()
                    del self.executors[session_id]
                    logger.debug(f"Executor cleaned up for session {session_id}")
                else:
                    logger.warning(f"Session {session_id} not found in executors")
            
            # Unregister session
            if self.registry.unregister(session_id):
                logger.info(f"Session {session_id} unregistered, remaining sessions: {self.registry.count()}")
            else:
                logger.warning(f"Session {session_id} not found in registry")
        
        return {'type': 'status', 'status': 'ok'}
    
    def _handle_event_request(self, message: Dict) -> Dict:
        """Handle event request."""
        # For now, just return status
        return {'type': 'status', 'status': 'ok'}


def start_server(port: int = DEFAULT_PORT, host: str = 'localhost') -> SocketServer:
    """Start the PyTrace agent server.
    
    Args:
        port: Port to listen on
        host: Host to bind to
    
    Returns:
        SocketServer instance
    """
    logger.info(f"Creating and starting PyTrace server on {host}:{port}")
    server = SocketServer(port, host)
    server.start()
    logger.info(f"PyTrace server started successfully on {host}:{port}")
    return server

