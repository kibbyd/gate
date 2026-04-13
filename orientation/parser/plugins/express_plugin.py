"""
Express Framework Plugin - Detects and extracts Express routes, middleware, and controllers
"""
import os
import re
from typing import Dict, List, Any
from parser.base_plugin import FrameworkPlugin, PluginMetadata


class ExpressPlugin(FrameworkPlugin):
    """Detect and extract Express routes, middleware, and API structure"""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="express",
            category="framework",
            language="javascript",
            file_extensions=[".js", ".ts", ".mjs"],
            package_indicators=["express"]
        )

    def detect(self, file_content: str, file_path: str) -> bool:
        """
        Returns True if file contains Express code

        Checks for:
        - require('express') or import express
        - app.get/post/put/delete
        - router.get/post/put/delete
        - app.use (middleware)
        """
        # Check for Express import/require
        if re.search(r"require\s*\(\s*['\"]express['\"]\s*\)", file_content):
            return True
        if re.search(r"from\s+['\"]express['\"]", file_content):
            return True

        # Check for Express routing methods
        if re.search(r'\b(app|router)\.(get|post|put|delete|patch|use)\s*\(', file_content):
            return True

        return False

    def extract(self, file_content: str, file_path: str, root_dir: str) -> Dict[str, Any]:
        """
        Extract Express-specific data from file

        Returns:
            {
                "routes": [list of route objects],
                "middleware": [list of middleware],
                "controllers": [list of controller functions]
            }
        """
        rel_path = os.path.relpath(file_path, root_dir)

        results = {
            "routes": [],
            "middleware": [],
            "controllers": []
        }

        # Extract routes
        routes = self._extract_routes(file_content, rel_path)
        results["routes"].extend(routes)

        # Extract middleware
        middleware = self._extract_middleware(file_content, rel_path)
        results["middleware"].extend(middleware)

        # Extract controller functions
        controllers = self._extract_controllers(file_content, rel_path)
        results["controllers"].extend(controllers)

        return results

    def _extract_routes(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract Express route definitions"""
        routes = []

        # Pattern: app.get('/path', handler) or router.post('/api/users', controller.create)
        # Matches: app.METHOD('path', ...
        route_pattern = r'\b(app|router)\.(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*([^)]+)\)'

        for match in re.finditer(route_pattern, content):
            router_type = match.group(1)  # 'app' or 'router'
            method = match.group(2).upper()  # GET, POST, etc.
            path = match.group(3)  # '/api/users'
            handler = match.group(4).strip()  # 'controller.create' or 'async (req, res) => {...}'

            line_num = content[:match.start()].count('\n') + 1

            # Determine if it's an inline handler or controller reference
            is_inline = 'async' in handler or 'function' in handler or '=>' in handler

            # Extract route parameters
            params = re.findall(r':(\w+)', path)

            route = {
                "id": f"{file_path}:{method}:{path}",
                "method": method,
                "path": path,
                "file": file_path,
                "line": line_num,
                "handler": handler.split('\n')[0][:50],  # First 50 chars
                "handlerType": "inline" if is_inline else "controller",
                "routerType": router_type,
                "parameters": params,
                "middleware": self._extract_route_middleware(content, match.start())
            }
            routes.append(route)

        return routes

    def _extract_middleware(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract Express middleware (app.use)"""
        middleware = []

        # Pattern: app.use(...) or app.use('/path', ...)
        middleware_pattern = r'\b(app|router)\.use\s*\(([^)]+)\)'

        for match in re.finditer(middleware_pattern, content):
            router_type = match.group(1)
            args = match.group(2).strip()

            line_num = content[:match.start()].count('\n') + 1

            # Check if it has a path prefix
            path_match = re.match(r"['\"]([^'\"]+)['\"]", args)
            path = path_match.group(1) if path_match else None

            # Extract middleware name
            middleware_name = self._extract_middleware_name(args)

            mw = {
                "id": f"{file_path}:middleware:{line_num}",
                "name": middleware_name,
                "file": file_path,
                "line": line_num,
                "path": path,
                "routerType": router_type,
                "type": self._classify_middleware(middleware_name)
            }
            middleware.append(mw)

        return middleware

    def _extract_controllers(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract controller functions (exported functions that handle routes)"""
        controllers = []

        # Pattern 1: exports.functionName = async (req, res) => {...}
        export_pattern = r'exports\.(\w+)\s*=\s*(async\s+)?\(([^)]*)\)\s*=>'
        for match in re.finditer(export_pattern, content):
            func_name = match.group(1)
            is_async = match.group(2) is not None
            params = match.group(3).strip()
            line_num = content[:match.start()].count('\n') + 1

            controller = {
                "id": f"{file_path}:{func_name}",
                "name": func_name,
                "file": file_path,
                "line": line_num,
                "isAsync": is_async,
                "parameters": [p.strip() for p in params.split(',') if p.strip()],
                "type": "arrow"
            }
            controllers.append(controller)

        # Pattern 2: exports.functionName = function(req, res) {...}
        export_func_pattern = r'exports\.(\w+)\s*=\s*(async\s+)?function\s*\(([^)]*)\)'
        for match in re.finditer(export_func_pattern, content):
            func_name = match.group(1)
            is_async = match.group(2) is not None
            params = match.group(3).strip()
            line_num = content[:match.start()].count('\n') + 1

            controller = {
                "id": f"{file_path}:{func_name}",
                "name": func_name,
                "file": file_path,
                "line": line_num,
                "isAsync": is_async,
                "parameters": [p.strip() for p in params.split(',') if p.strip()],
                "type": "function"
            }
            controllers.append(controller)

        # Pattern 3: export const functionName = async (req, res) => {...}
        export_const_pattern = r'export\s+const\s+(\w+)\s*=\s*(async\s+)?\(([^)]*)\)\s*=>'
        for match in re.finditer(export_const_pattern, content):
            func_name = match.group(1)
            is_async = match.group(2) is not None
            params = match.group(3).strip()
            line_num = content[:match.start()].count('\n') + 1

            controller = {
                "id": f"{file_path}:{func_name}",
                "name": func_name,
                "file": file_path,
                "line": line_num,
                "isAsync": is_async,
                "parameters": [p.strip() for p in params.split(',') if p.strip()],
                "type": "arrow"
            }
            controllers.append(controller)

        return controllers

    def _extract_route_middleware(self, content: str, route_start: int) -> List[str]:
        """Extract middleware applied to a specific route"""
        # Look for middleware between method and handler
        # Example: app.get('/path', auth, validate, handler)
        # This is a simplified version - could be enhanced
        remaining = content[route_start:route_start + 200]

        # Find all identifiers between first and last comma
        middleware_names = []
        parts = remaining.split(',')
        if len(parts) > 2:  # Has middleware between path and handler
            for part in parts[1:-1]:  # Skip path and handler
                # Extract identifier
                match = re.search(r'\b([a-zA-Z_]\w+)\b', part)
                if match:
                    middleware_names.append(match.group(1))

        return middleware_names

    def _extract_middleware_name(self, args: str) -> str:
        """Extract middleware name from app.use arguments"""
        # Common patterns:
        # app.use(express.json()) -> express.json
        # app.use(cors()) -> cors
        # app.use(myMiddleware) -> myMiddleware
        # app.use('/api', apiRouter) -> apiRouter

        # Remove path if present
        if args.startswith("'") or args.startswith('"'):
            parts = args.split(',', 1)
            if len(parts) > 1:
                args = parts[1].strip()

        # Extract function/method name
        match = re.search(r'([a-zA-Z_][\w.]+)', args)
        if match:
            return match.group(1)

        return "unknown"

    def _classify_middleware(self, name: str) -> str:
        """Classify middleware by type"""
        name_lower = name.lower()

        if 'cors' in name_lower:
            return "cors"
        elif 'json' in name_lower or 'urlencoded' in name_lower:
            return "body-parser"
        elif 'auth' in name_lower or 'passport' in name_lower or 'jwt' in name_lower:
            return "authentication"
        elif 'morgan' in name_lower or 'logger' in name_lower:
            return "logging"
        elif 'router' in name_lower:
            return "router"
        elif 'static' in name_lower:
            return "static-files"
        elif 'session' in name_lower:
            return "session"
        elif 'helmet' in name_lower:
            return "security"
        else:
            return "custom"
