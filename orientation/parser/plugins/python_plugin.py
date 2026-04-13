"""
Python Language Parser Plugin

Uses Python's AST (Abstract Syntax Tree) module to parse Python files
and extract functions, classes, methods, decorators, and API endpoints.
"""

import ast
import os
from typing import Dict, List, Any
from parser.base_plugin import LanguageParser


class PythonParser(LanguageParser):
    """Parser for Python language using AST."""

    @property
    def language(self) -> str:
        return "python"

    @property
    def file_extensions(self) -> List[str]:
        return [".py"]

    def parse_file(self, file_path: str, root_dir: str) -> Dict[str, Any]:
        """
        Parse a single Python file using AST.

        Returns:
            {
                "functions": [...],
                "classes": [...],
                "imports": [...],
                "endpoints": [...]  # FastAPI/Django/Flask routes
            }
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                source_code = f.read()

            # Parse the AST
            tree = ast.parse(source_code, filename=file_path)

            # Get relative path
            rel_path = os.path.relpath(file_path, root_dir)

            # Extract information
            functions = []
            classes = []
            imports = []
            endpoints = []

            for node in ast.walk(tree):
                # Extract imports
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append({
                            "module": alias.name,
                            "alias": alias.asname,
                            "line": node.lineno
                        })
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        imports.append({
                            "module": f"{module}.{alias.name}" if module else alias.name,
                            "alias": alias.asname,
                            "from": module,
                            "line": node.lineno
                        })

            # Extract top-level functions and classes
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    func_data = self._extract_function(node, rel_path, file_path)
                    functions.append(func_data)

                    # Check for API endpoint decorators
                    endpoint = self._extract_endpoint(node, rel_path, file_path)
                    if endpoint:
                        endpoints.append(endpoint)

                elif isinstance(node, ast.ClassDef):
                    class_data = self._extract_class(node, rel_path, file_path)
                    classes.append(class_data)

            return {
                "functions": functions,
                "classes": classes,
                "imports": imports,
                "endpoints": endpoints
            }

        except SyntaxError as e:
            # File has syntax errors, skip it
            return {"functions": [], "classes": [], "imports": [], "endpoints": []}
        except Exception as e:
            # Other errors, skip file
            return {"functions": [], "classes": [], "imports": [], "endpoints": []}

    def _extract_function(self, node, rel_path: str, file_path: str) -> Dict[str, Any]:
        """Extract function information from AST node."""
        # Get decorators
        decorators = [self._get_decorator_name(d) for d in node.decorator_list]

        # Get arguments
        args = []
        if node.args.args:
            for arg in node.args.args:
                arg_name = arg.arg
                arg_type = self._get_annotation(arg.annotation) if arg.annotation else None
                args.append({"name": arg_name, "type": arg_type})

        # Get docstring
        docstring = ast.get_docstring(node)

        # Get return type
        return_type = self._get_annotation(node.returns) if node.returns else None

        # Check if async
        is_async = isinstance(node, ast.AsyncFunctionDef)

        # Build signature
        args_str = ", ".join([a["name"] for a in args])
        signature = f"{'async ' if is_async else ''}def {node.name}({args_str})"
        if return_type:
            signature += f" -> {return_type}"

        return {
            "id": f"{rel_path}:{node.name}",
            "name": node.name,
            "file": rel_path,
            "line": node.lineno,
            "signature": signature,
            "decorators": decorators,
            "arguments": args,
            "return_type": return_type,
            "docstring": docstring,
            "is_async": is_async,
            "calls": self._extract_function_calls(node)
        }

    def _extract_class(self, node, rel_path: str, file_path: str) -> Dict[str, Any]:
        """Extract class information from AST node."""
        # Get base classes
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(self._get_attribute_name(base))

        # Get decorators
        decorators = [self._get_decorator_name(d) for d in node.decorator_list]

        # Get docstring
        docstring = ast.get_docstring(node)

        # Extract methods
        methods = []
        for item in node.body:
            if isinstance(item, ast.FunctionDef) or isinstance(item, ast.AsyncFunctionDef):
                method_data = self._extract_function(item, rel_path, file_path)
                method_data["id"] = f"{rel_path}:{node.name}.{item.name}"
                methods.append(method_data)

        return {
            "id": f"{rel_path}:{node.name}",
            "name": node.name,
            "file": rel_path,
            "line": node.lineno,
            "bases": bases,
            "decorators": decorators,
            "docstring": docstring,
            "methods": methods
        }

    def _extract_endpoint(self, node, rel_path: str, file_path: str) -> Dict[str, Any]:
        """
        Extract API endpoint information from decorators.
        Supports FastAPI, Flask, and Django.
        """
        for decorator in node.decorator_list:
            decorator_name = self._get_decorator_name(decorator)

            # FastAPI patterns: @app.get("/path"), @router.post("/path")
            if isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Attribute):
                    method_name = decorator.func.attr.upper()
                    # Check if it's an HTTP method
                    if method_name in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD']:
                        # Get the path from first argument
                        path = None
                        if decorator.args:
                            if isinstance(decorator.args[0], ast.Str):
                                path = decorator.args[0].s
                            elif isinstance(decorator.args[0], ast.Constant):
                                path = decorator.args[0].value

                        if path:
                            return {
                                "id": f"{rel_path}:{method_name}:{path}",
                                "method": method_name,
                                "path": path,
                                "handler": node.name,
                                "file": rel_path,
                                "line": node.lineno,
                                "framework": "fastapi",
                                "is_async": isinstance(node, ast.AsyncFunctionDef)
                            }

            # Flask pattern: @app.route("/path", methods=["GET"])
            if decorator_name == "route" and isinstance(decorator, ast.Call):
                if decorator.args:
                    path = None
                    if isinstance(decorator.args[0], ast.Str):
                        path = decorator.args[0].s
                    elif isinstance(decorator.args[0], ast.Constant):
                        path = decorator.args[0].value

                    # Get methods from kwargs
                    methods = ["GET"]  # default
                    for keyword in decorator.keywords:
                        if keyword.arg == "methods":
                            if isinstance(keyword.value, ast.List):
                                methods = [self._get_constant_value(m) for m in keyword.value.elts]

                    if path:
                        return {
                            "id": f"{rel_path}:{methods[0]}:{path}",
                            "method": methods[0],
                            "path": path,
                            "handler": node.name,
                            "file": rel_path,
                            "line": node.lineno,
                            "framework": "flask",
                            "methods": methods
                        }

        return None

    def _extract_function_calls(self, node) -> List[str]:
        """Extract function calls within a function."""
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(self._get_attribute_name(child.func))
        # Return unique calls
        return list(set(calls))

    def _get_decorator_name(self, decorator) -> str:
        """Get decorator name as string."""
        if isinstance(decorator, ast.Name):
            return decorator.id
        elif isinstance(decorator, ast.Attribute):
            return self._get_attribute_name(decorator)
        elif isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name):
                return decorator.func.id
            elif isinstance(decorator.func, ast.Attribute):
                return self._get_attribute_name(decorator.func)
        return "unknown"

    def _get_attribute_name(self, node) -> str:
        """Get full attribute name (e.g., 'app.route')."""
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))

    def _get_annotation(self, node) -> str:
        """Get type annotation as string."""
        if node is None:
            return None
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_attribute_name(node)
        elif isinstance(node, ast.Subscript):
            # Handle List[int], Dict[str, int], etc.
            value = self._get_annotation(node.value)
            slice_val = self._get_annotation(node.slice)
            return f"{value}[{slice_val}]"
        elif isinstance(node, ast.Tuple):
            # Handle Tuple[int, str]
            elts = [self._get_annotation(e) for e in node.elts]
            return ", ".join(elts)
        elif isinstance(node, ast.Constant):
            return str(node.value)
        return "unknown"

    def _get_constant_value(self, node):
        """Get constant value from AST node."""
        if isinstance(node, ast.Str):
            return node.s
        elif isinstance(node, ast.Constant):
            return node.value
        return None

    def parse_directory(self, root_dir: str, verbose: bool = True) -> Dict[str, Any]:
        """
        Parse entire directory recursively.

        Returns:
            {
                "functions": [...],
                "classes": [...],
                "endpoints": [...],
                "imports": [...]
            }
        """
        if verbose:
            print(f"🐍 Parsing Python files in: {root_dir}")

        all_functions = []
        all_classes = []
        all_endpoints = []
        all_imports = []
        file_count = 0

        # Directories to skip
        skip_dirs = {'__pycache__', '.git', '.venv', 'venv', 'node_modules', 'dist', 'build'}

        for dirpath, dirnames, filenames in os.walk(root_dir):
            # Filter directories
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]

            for filename in filenames:
                if filename.endswith('.py'):
                    file_path = os.path.join(dirpath, filename)
                    file_count += 1

                    if verbose and file_count % 10 == 0:
                        print(f"   Parsed {file_count} Python files...", end='\r')

                    result = self.parse_file(file_path, root_dir)

                    all_functions.extend(result.get('functions', []))
                    all_classes.extend(result.get('classes', []))
                    all_endpoints.extend(result.get('endpoints', []))
                    all_imports.extend(result.get('imports', []))

        if verbose:
            print(f"   ✅ Parsed {file_count} Python files" + " " * 20)
            print(f"   Found: {len(all_functions)} functions, {len(all_classes)} classes, {len(all_endpoints)} endpoints")

        return {
            "functions": all_functions,
            "classes": all_classes,
            "endpoints": all_endpoints,
            "imports": all_imports
        }
