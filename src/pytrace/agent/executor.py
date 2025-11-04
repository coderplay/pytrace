"""Script execution engine for PyTrace."""

import ast
import threading
import time
from typing import Dict, Any, Callable, Optional
from io import StringIO
import sys

from pytrace.core import builtins, decorators


class ScriptExecutor:
    """Executes PyTrace scripts in a sandboxed environment."""
    
    def __init__(self, session_id: str, print_callback: Optional[Callable[[str], None]] = None):
        """
        Initialize executor.
        
        Args:
            session_id: Session ID for this execution
            print_callback: Callback function for print output
        """
        self.session_id = session_id
        self.print_callback = print_callback
        self.globals: Dict[str, Any] = {}
        self.namespace: Dict[str, Any] = {}
        self.timers: list = []
        self._lock = threading.RLock()
        
        # Setup sandboxed environment
        self._setup_namespace()
    
    def _setup_namespace(self):
        """Setup the sandboxed namespace for script execution."""
        # Import built-in functions
        self.namespace.update({
            'count': builtins.count,
            'avg': builtins.avg,
            'histo': builtins.histo,
            'topk': builtins.topk,
            'now': builtins.now,
        })
        
        # Setup print function that redirects to callback
        def safe_print(*args, **kwargs):
            """Redirect print to callback."""
            output = StringIO()
            print(*args, file=output, **kwargs)
            message = output.getvalue()
            if self.print_callback:
                self.print_callback(message.rstrip())
        
        self.namespace['print'] = safe_print
        
        # Import decorators
        self.namespace.update({
            'function_entry': decorators.function_entry,
            'function_return': decorators.function_return,
            'on_exception': decorators.on_exception,
            'timer': decorators.timer,
            'pytrace': type('pytrace', (), {}),  # Dummy module for import pytrace
        })
        
        # Setup context
        self.namespace['ctx'] = decorators.get_context()
    
    def execute(self, script_content: str, args: list) -> Dict[str, Any]:
        """
        Execute a script and return compiled handlers.
        
        Args:
            script_content: Source code of the script
            args: Arguments passed to the script
        
        Returns:
            Dictionary containing:
            - 'globals': Global variables from script
            - 'namespace': Execution namespace
            - 'handlers': Compiled handlers organized by type
        """
        try:
            # Parse script
            tree = ast.parse(script_content, filename='<script>')
            
            # Execute script in sandboxed namespace
            # This will register decorators and create global variables
            code = compile(tree, '<script>', 'exec')
            exec(code, self.namespace)
            
            # Extract global variables (user-defined data structures)
            # These are variables defined at module level that aren't functions
            for name in self.namespace:
                if not name.startswith('_') and name not in self.namespace:
                    if not callable(self.namespace[name]) or name in ('ctx',):
                        self.globals[name] = self.namespace[name]
            
            # Get handlers from decorators
            handlers = decorators.get_handlers()
            
            # Setup timers
            self._setup_timers(handlers.get('timer', []))
            
            return {
                'globals': self.globals,
                'namespace': self.namespace,
                'handlers': {
                    'function_entry': dict(handlers['function_entry']),
                    'function_return': dict(handlers['function_return']),
                    'on_exception': dict(handlers['on_exception']),
                    'timer': handlers['timer'],
                }
            }
        except Exception as e:
            # Error isolation - don't crash the target process
            error_msg = f"Script execution error: {e}"
            if self.print_callback:
                self.print_callback(error_msg)
            raise
    
    def _setup_timers(self, timer_handlers: list):
        """Setup timer callbacks."""
        def run_timer(handler_func: Callable, interval_ms: int):
            """Run timer callback periodically."""
            def timer_callback():
                try:
                    # Execute handler in the script's namespace
                    with self._lock:
                        # Update namespace with current globals
                        self.namespace.update(self.globals)
                        handler_func()
                        # Update globals from namespace
                        for key, value in self.namespace.items():
                            if key not in ('ctx', 'print', 'count', 'avg', 'histo', 'topk', 'now',
                                         'function_entry', 'function_return', 'on_exception', 'timer', 'pytrace'):
                                if not callable(value) or key in self.globals:
                                    self.globals[key] = value
                except Exception as e:
                    if self.print_callback:
                        self.print_callback(f"Timer error: {e}")
                finally:
                    # Schedule next execution
                    if interval_ms > 0:
                        timer = threading.Timer(interval_ms / 1000.0, timer_callback)
                        timer.daemon = True
                        timer.start()
                        self.timers.append(timer)
            
            # Start first execution
            timer_callback()
        
        # Start all timers
        for timer_info in timer_handlers:
            handler_func = timer_info['function']
            interval_ms = timer_info['interval_ms']
            timer = threading.Timer(interval_ms / 1000.0, lambda: run_timer(handler_func, interval_ms))
            timer.daemon = True
            timer.start()
            self.timers.append(timer)
    
    def invoke_handler(self, handler_type: str, pattern: str, *args, **kwargs):
        """
        Invoke handlers for a given pattern.
        
        Args:
            handler_type: 'function_entry', 'function_return', or 'on_exception'
            pattern: Function pattern to match
            *args, **kwargs: Arguments to pass to handlers
        """
        try:
            handlers = decorators.get_handlers()
            handler_list = handlers.get(handler_type, {}).get(pattern, [])
            
            for handler_func in handler_list:
                try:
                    # Update namespace with current globals
                    with self._lock:
                        self.namespace.update(self.globals)
                        # Update context
                        self.namespace['ctx'] = decorators.get_context()
                        # Invoke handler
                        handler_func(*args, **kwargs)
                        # Update globals from namespace
                        for key, value in self.namespace.items():
                            if key not in ('ctx', 'print', 'count', 'avg', 'histo', 'topk', 'now',
                                         'function_entry', 'function_return', 'on_exception', 'timer', 'pytrace'):
                                if not callable(value) or key in self.globals:
                                    self.globals[key] = value
                except Exception as e:
                    if self.print_callback:
                        self.print_callback(f"Handler error ({handler_type}/{pattern}): {e}")
        except Exception as e:
            if self.print_callback:
                self.print_callback(f"Error invoking handlers: {e}")
    
    def cleanup(self):
        """Cleanup resources (stop timers, etc.)."""
        with self._lock:
            for timer in self.timers:
                timer.cancel()
            self.timers.clear()
            decorators.clear_context()

