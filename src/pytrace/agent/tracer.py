"""sys.monitoring integration for PyTrace."""

import sys
import threading
from typing import Dict, Callable, Optional, Any
from types import FrameType

from pytrace.agent.registry import SessionRegistry
from pytrace.core.decorators import get_context, clear_context


class Tracer:
    """Tracer using sys.monitoring for function entry/exit/exception events."""
    
    def __init__(self, registry: SessionRegistry):
        """
        Initialize tracer.
        
        Args:
            registry: Session registry to query for active scripts
        """
        self.registry = registry
        self.tool_id = sys.monitoring.use_tool_id("pytrace")
        self._lock = threading.RLock()
        self._enabled = False
        
        # Get monitoring events constants
        self.PY_START = sys.monitoring.events.PY_START
        self.PY_RETURN = sys.monitoring.events.PY_RETURN
        self.PY_THROW = sys.monitoring.events.PY_THROW
    
    def start(self):
        """Start monitoring."""
        with self._lock:
            if self._enabled:
                return
            
            # Register callbacks
            sys.monitoring.register_callback(
                self.tool_id, self.PY_START, self._on_function_start
            )
            sys.monitoring.register_callback(
                self.tool_id, self.PY_RETURN, self._on_function_return
            )
            sys.monitoring.register_callback(
                self.tool_id, self.PY_THROW, self._on_function_exception
            )
            
            # Enable events
            sys.monitoring.set_events(self.tool_id, self.PY_START | self.PY_RETURN | self.PY_THROW)
            
            self._enabled = True
    
    def stop(self):
        """Stop monitoring."""
        with self._lock:
            if not self._enabled:
                return
            
            # Disable events
            sys.monitoring.set_events(self.tool_id, 0)
            
            # Unregister callbacks
            sys.monitoring.register_callback(self.tool_id, self.PY_START, None)
            sys.monitoring.register_callback(self.tool_id, self.PY_RETURN, None)
            sys.monitoring.register_callback(self.tool_id, self.PY_THROW, None)
            
            self._enabled = False
    
    def _on_function_start(self, code: Any, instruction_offset: int):
        """Handle PY_START event (function entry)."""
        try:
            frame = sys._getframe(1)  # Get caller frame
            
            # Get function name
            func_name = self._get_function_name(frame)
            if not func_name:
                return
            
            # Query registry for matching handlers
            patterns = self.registry.get_all_patterns('function_entry')
            
            # Find matching patterns
            matching_handlers = []
            for pattern, handler_list in patterns.items():
                if self._match_pattern(func_name, pattern):
                    matching_handlers.extend(handler_list)
            
            if not matching_handlers:
                return
            
            # Clear context for new invocation
            clear_context()
            ctx = get_context()
            
            # Extract function arguments
            args = self._extract_args(frame)
            
            # Store args in context for handler access
            ctx['args'] = args
            
            # Invoke handlers for each matching session
            sessions = self.registry.get_all_sessions()
            for session_id, session_data in sessions.items():
                handlers = session_data.get('handlers', {})
                handler_list = handlers.get('function_entry', {}).get(func_name, [])
                
                for handler_func in handler_list:
                    try:
                        # Get executor if available, otherwise use session data
                        executor = session_data.get('executor')
                        if executor:
                            # Use executor's namespace which has proper closure
                            with executor._lock:
                                executor.namespace.update(executor.globals)
                                executor.namespace['ctx'] = ctx
                                executor.namespace['args'] = args
                                # Invoke handler
                                handler_func(args)
                                # Update globals from namespace
                                for key, value in executor.namespace.items():
                                    if key not in ('ctx', 'args', 'print', 'count', 'avg', 'histo', 'topk', 'now',
                                                 'function_entry', 'function_return', 'on_exception', 'timer', 'pytrace'):
                                        if not callable(value) or key in executor.globals:
                                            executor.globals[key] = value
                                # Update session data
                                session_data['globals'] = executor.globals
                                session_data['namespace'] = executor.namespace
                        else:
                            # Fallback: use session data directly
                            namespace = session_data.get('namespace', {})
                            exec_globals = session_data.get('globals', {})
                            namespace.update(exec_globals)
                            namespace['ctx'] = ctx
                            namespace['args'] = args
                            handler_func(args)
                            for key, value in namespace.items():
                                if key not in ('ctx', 'args', 'print', 'count', 'avg', 'histo', 'topk', 'now',
                                             'function_entry', 'function_return', 'on_exception', 'timer', 'pytrace'):
                                    if not callable(value) or key in exec_globals:
                                        exec_globals[key] = value
                    except Exception as e:
                        # Error isolation - don't crash target process
                        pass
        except Exception:
            # Error isolation
            pass
    
    def _on_function_return(self, code: Any, instruction_offset: int, retval: Any):
        """Handle PY_RETURN event (function return)."""
        try:
            frame = sys._getframe(1)  # Get caller frame
            
            # Get function name
            func_name = self._get_function_name(frame)
            if not func_name:
                return
            
            # Query registry for matching handlers
            patterns = self.registry.get_all_patterns('function_return')
            
            # Find matching patterns
            matching_patterns = []
            for pattern in patterns.keys():
                if self._match_pattern(func_name, pattern):
                    matching_patterns.append(pattern)
            
            if not matching_patterns:
                return
            
            ctx = get_context()
            
            # Invoke handlers for each matching session
            sessions = self.registry.get_all_sessions()
            for session_id, session_data in sessions.items():
                handlers = session_data.get('handlers', {})
                
                for pattern in matching_patterns:
                    handler_list = handlers.get('function_return', {}).get(pattern, [])
                    
                    for handler_func in handler_list:
                        try:
                            executor = session_data.get('executor')
                            if executor:
                                with executor._lock:
                                    executor.namespace.update(executor.globals)
                                    executor.namespace['ctx'] = ctx
                                    executor.namespace['retval'] = retval
                                    handler_func(retval)
                                    for key, value in executor.namespace.items():
                                        if key not in ('ctx', 'retval', 'print', 'count', 'avg', 'histo', 'topk', 'now',
                                                     'function_entry', 'function_return', 'on_exception', 'timer', 'pytrace'):
                                            if not callable(value) or key in executor.globals:
                                                executor.globals[key] = value
                                    session_data['globals'] = executor.globals
                                    session_data['namespace'] = executor.namespace
                            else:
                                namespace = session_data.get('namespace', {})
                                exec_globals = session_data.get('globals', {})
                                namespace.update(exec_globals)
                                namespace['ctx'] = ctx
                                namespace['retval'] = retval
                                handler_func(retval)
                                for key, value in namespace.items():
                                    if key not in ('ctx', 'retval', 'print', 'count', 'avg', 'histo', 'topk', 'now',
                                                 'function_entry', 'function_return', 'on_exception', 'timer', 'pytrace'):
                                        if not callable(value) or key in exec_globals:
                                            exec_globals[key] = value
                        except Exception:
                            pass
        except Exception:
            pass
    
    def _on_function_exception(self, code: Any, instruction_offset: int, exc: Exception):
        """Handle PY_THROW event (exception)."""
        try:
            frame = sys._getframe(1)
            
            func_name = self._get_function_name(frame)
            if not func_name:
                return
            
            patterns = self.registry.get_all_patterns('on_exception')
            
            matching_patterns = []
            for pattern in patterns.keys():
                if self._match_pattern(func_name, pattern):
                    matching_patterns.append(pattern)
            
            if not matching_patterns:
                return
            
            ctx = get_context()
            
            sessions = self.registry.get_all_sessions()
            for session_id, session_data in sessions.items():
                handlers = session_data.get('handlers', {})
                
                for pattern in matching_patterns:
                    handler_list = handlers.get('on_exception', {}).get(pattern, [])
                    
                    for handler_func in handler_list:
                        try:
                            executor = session_data.get('executor')
                            if executor:
                                with executor._lock:
                                    executor.namespace.update(executor.globals)
                                    executor.namespace['ctx'] = ctx
                                    executor.namespace['exc'] = exc
                                    handler_func(exc)
                                    for key, value in executor.namespace.items():
                                        if key not in ('ctx', 'exc', 'print', 'count', 'avg', 'histo', 'topk', 'now',
                                                     'function_entry', 'function_return', 'on_exception', 'timer', 'pytrace'):
                                            if not callable(value) or key in executor.globals:
                                                executor.globals[key] = value
                                    session_data['globals'] = executor.globals
                                    session_data['namespace'] = executor.namespace
                            else:
                                namespace = session_data.get('namespace', {})
                                exec_globals = session_data.get('globals', {})
                                namespace.update(exec_globals)
                                namespace['ctx'] = ctx
                                namespace['exc'] = exc
                                handler_func(exc)
                                for key, value in namespace.items():
                                    if key not in ('ctx', 'exc', 'print', 'count', 'avg', 'histo', 'topk', 'now',
                                                 'function_entry', 'function_return', 'on_exception', 'timer', 'pytrace'):
                                        if not callable(value) or key in exec_globals:
                                            exec_globals[key] = value
                        except Exception:
                            pass
        except Exception:
            pass
    
    def _get_function_name(self, frame: FrameType) -> Optional[str]:
        """Extract function name from frame."""
        try:
            code = frame.f_code
            func_name = code.co_name
            
            # Get module name
            module_name = frame.f_globals.get('__name__', '')
            
            # Construct full name
            if module_name:
                return f"{module_name}.{func_name}"
            return func_name
        except Exception:
            return None
    
    def _extract_args(self, frame: FrameType) -> Dict[str, Any]:
        """Extract function arguments from frame."""
        try:
            code = frame.f_code
            arg_names = code.co_varnames[:code.co_argcount]
            args = {}
            
            for name in arg_names:
                if name in frame.f_locals:
                    args[name] = frame.f_locals[name]
            
            # Handle *args and **kwargs if present
            if code.co_flags & 0x04:  # CO_VARARGS
                varargs_idx = code.co_argcount
                if varargs_idx < len(code.co_varnames):
                    varargs_name = code.co_varnames[varargs_idx]
                    if varargs_name in frame.f_locals:
                        args['*args'] = frame.f_locals[varargs_name]
            
            if code.co_flags & 0x08:  # CO_VARKEYWORDS
                varkw_idx = code.co_argcount + (1 if code.co_flags & 0x04 else 0)
                if varkw_idx < len(code.co_varnames):
                    varkw_name = code.co_varnames[varkw_idx]
                    if varkw_name in frame.f_locals:
                        args['**kwargs'] = frame.f_locals[varkw_name]
            
            return args
        except Exception:
            return {}
    
    def _match_pattern(self, func_name: str, pattern: str) -> bool:
        """Match function name against pattern."""
        # For MVP: exact match
        # TODO: Support wildcards in future
        return func_name == pattern

