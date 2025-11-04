"""Validator for restricted Python scripts."""

import ast
from typing import List, Set, Tuple, Dict, Any
import sys


class ValidationError(Exception):
    """Raised when script validation fails."""
    pass


class ScriptValidator(ast.NodeVisitor):
    """Validates PyTrace scripts for safety restrictions."""
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.handlers: List[Tuple[str, str]] = []  # (decorator_name, pattern)
        self.allowed_imports = {'pytrace'}
        self.allowed_builtins = {
            'len', 'range', 'str', 'int', 'float', 'bool', 'list', 'dict',
            'getattr', 'hasattr', 'isinstance', 'type', 'print'
        }
        self.in_function = False
        self.in_handler = False
        
    def validate(self, script_source: str) -> Tuple[bool, List[str], List[Tuple[str, str]]]:
        """
        Validate a script.
        
        Returns:
            (is_valid, errors, handlers)
        """
        try:
            tree = ast.parse(script_source, filename='<script>')
            self.visit(tree)
        except SyntaxError as e:
            self.errors.append(f"Syntax error: {e}")
        
        handlers = self.handlers.copy()
        errors = self.errors.copy()
        
        # Reset state
        self.errors = []
        self.handlers = []
        self.in_function = False
        self.in_handler = False
        
        return len(errors) == 0, errors, handlers
    
    def visit_Module(self, node: ast.Module):
        """Visit module-level nodes."""
        self.generic_visit(node)
    
    def visit_Import(self, node: ast.Import):
        """Check imports."""
        for alias in node.names:
            if alias.name not in self.allowed_imports:
                self.errors.append(f"Import '{alias.name}' is not allowed. Only 'pytrace' is allowed.")
    
    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Check imports from."""
        if node.module and node.module not in self.allowed_imports:
            self.errors.append(f"Import from '{node.module}' is not allowed. Only 'pytrace' is allowed.")
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Check function definitions."""
        # Check if this is a handler function (has decorators)
        is_handler = False
        handler_info = None
        
        for decorator in node.decorator_list:
            decorator_name = self._get_decorator_name(decorator)
            if decorator_name in ('function_entry', 'function_return', 'on_exception', 'timer'):
                is_handler = True
                if decorator_name != 'timer':
                    pattern = self._get_decorator_arg(decorator)
                    if pattern:
                        self.handlers.append((decorator_name, pattern))
                        handler_info = (decorator_name, pattern)
                else:
                    interval = self._get_decorator_arg(decorator)
                    if interval:
                        self.handlers.append((decorator_name, str(interval)))
                        handler_info = (decorator_name, str(interval))
        
        if not is_handler:
            self.errors.append(f"Function '{node.name}' is not a handler function. Only handler functions with decorators are allowed.")
            return
        
        # Handler functions are allowed
        self.in_function = True
        self.in_handler = True
        self.generic_visit(node)
        self.in_function = False
        self.in_handler = False
    
    def visit_ClassDef(self, node: ast.ClassDef):
        """Class definitions are not allowed."""
        self.errors.append(f"Class definitions are not allowed: {node.name}")
    
    def visit_For(self, node: ast.For):
        """For loops are not allowed."""
        self.errors.append("For loops are not allowed in PyTrace scripts.")
    
    def visit_While(self, node: ast.While):
        """While loops are not allowed."""
        self.errors.append("While loops are not allowed in PyTrace scripts.")
    
    def visit_With(self, node: ast.With):
        """With statements are restricted."""
        # Only allow context managers for ctx
        for item in node.items:
            if isinstance(item.context_expr, ast.Name) and item.context_expr.id == 'ctx':
                continue
            self.errors.append("With statements are not allowed except for context management.")
    
    def visit_Call(self, node: ast.Call):
        """Check function calls."""
        # Check for unsafe function calls
        func_name = self._get_function_name(node.func)
        
        # Check for file I/O operations
        unsafe_calls = {
            'open', 'file', 'input', 'raw_input',
            'exec', 'eval', 'compile',
            'exit', 'quit',
            'threading.Thread', 'threading.start',
            'multiprocessing.Process', 'multiprocessing.start'
        }
        
        if func_name in unsafe_calls:
            self.errors.append(f"Unsafe function call: {func_name}")
        
        self.generic_visit(node)
    
    def visit_Assign(self, node: ast.Assign):
        """Check assignments."""
        # Check if assigning to non-global variables (except ctx)
        for target in node.targets:
            if isinstance(target, ast.Name):
                # Allow assignments to ctx dictionary
                if target.id == 'ctx':
                    continue
                # Allow assignments to global variables (will be checked at runtime)
                # But we can't easily determine if it's global here
                # This is a limitation - we'll rely on runtime checks
            elif isinstance(target, ast.Attribute):
                # Attribute assignments are allowed (e.g., ctx["key"] = value)
                pass
            elif isinstance(target, ast.Subscript):
                # Subscript assignments are allowed (e.g., list[0] = value)
                pass
        
        self.generic_visit(node)
    
    def visit_Delete(self, node: ast.Delete):
        """Check delete statements."""
        # Allow deletions (e.g., del list[i])
        self.generic_visit(node)
    
    def _get_decorator_name(self, node: ast.expr) -> str:
        """Extract decorator name from AST node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        elif isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return ""
    
    def _get_decorator_arg(self, node: ast.expr) -> Any:
        """Extract decorator argument from AST node."""
        if isinstance(node, ast.Call):
            if node.args:
                # Get first argument (the pattern)
                arg = node.args[0]
                if isinstance(arg, ast.Constant):
                    return arg.value
                elif isinstance(arg, ast.Str):  # Python < 3.8
                    return arg.s
        return None
    
    def _get_function_name(self, node: ast.expr) -> str:
        """Extract function name from AST node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_function_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Call):
            return self._get_function_name(node.func)
        return ""


def validate_script(script_source: str) -> Tuple[bool, List[str], List[Tuple[str, str]]]:
    """
    Validate a PyTrace script.
    
    Args:
        script_source: Source code of the script
    
    Returns:
        (is_valid, errors, handlers) where:
        - is_valid: True if script is valid
        - errors: List of error messages
        - handlers: List of (decorator_name, pattern) tuples
    
    Raises:
        ValidationError: If validation fails
    """
    validator = ScriptValidator()
    is_valid, errors, handlers = validator.validate(script_source)
    
    if not is_valid:
        error_msg = "Script validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        raise ValidationError(error_msg)
    
    return is_valid, errors, handlers

