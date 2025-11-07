"""Session registry for managing active tracing sessions."""

import threading
from typing import Dict, Optional, Any
import uuid


class SessionRegistry:
    """Thread-safe registry for managing tracing sessions."""
    
    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
    
    def register(self, script_content: str, args: list, handlers: Dict[str, Any], 
                 executor: Optional[Any] = None, session_id: Optional[str] = None) -> str:
        """
        Register a new tracing session.
        
        Args:
            script_content: The script content
            args: Script arguments
            handlers: Compiled handlers from the script
            executor: Optional executor instance for this session
            session_id: Optional session ID (if not provided, a new UUID will be generated)
        
        Returns:
            Session ID
        """
        if session_id is None:
            session_id = str(uuid.uuid4())
        
        with self._lock:
            self._sessions[session_id] = {
                'script_content': script_content,
                'args': args,
                'handlers': handlers,
                'globals': handlers.get('globals', {}),
                'namespace': handlers.get('namespace', {}),
            }
            if executor is not None:
                self._sessions[session_id]['executor'] = executor
        
        return session_id
    
    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session by ID."""
        with self._lock:
            return self._sessions.get(session_id)
    
    def get_all_sessions(self) -> Dict[str, Dict[str, Any]]:
        """Get all active sessions (thread-safe copy)."""
        with self._lock:
            return self._sessions.copy()
    
    def get_all_patterns(self, handler_type: str) -> Dict[str, list]:
        """
        Get all registered patterns for a handler type across all sessions.
        
        Args:
            handler_type: 'function_entry', 'function_return', or 'on_exception'
        
        Returns:
            Dictionary mapping patterns to lists of handler functions
        """
        patterns = {}
        
        with self._lock:
            for session_id, session_data in self._sessions.items():
                handlers = session_data.get('handlers', {})
                handler_registry = handlers.get(handler_type, {})
                
                for pattern, handler_list in handler_registry.items():
                    if pattern not in patterns:
                        patterns[pattern] = []
                    patterns[pattern].extend(handler_list)
        
        return patterns
    
    def unregister(self, session_id: str) -> bool:
        """
        Unregister a session.
        
        Returns:
            True if session was found and removed, False otherwise
        """
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False
    
    def clear(self):
        """Clear all sessions."""
        with self._lock:
            self._sessions.clear()
    
    def count(self) -> int:
        """Get number of active sessions."""
        with self._lock:
            return len(self._sessions)

