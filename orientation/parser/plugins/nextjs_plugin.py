"""
Next.js Framework Plugin - Detects and extracts Next.js App Router, Server Actions, API routes, and patterns
"""
import os
import re
from typing import Dict, List, Any
from parser.base_plugin import FrameworkPlugin, PluginMetadata


class NextJSPlugin(FrameworkPlugin):
    """Detect and extract Next.js App Router structure, Server Actions, and API routes"""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="nextjs",
            category="framework",
            language="javascript",
            file_extensions=[".jsx", ".tsx", ".js", ".ts"],
            package_indicators=["next"]
        )

    def detect(self, file_content: str, file_path: str) -> bool:
        """
        Returns True if file is part of a Next.js project

        Checks for:
        - 'use client' or 'use server' directives
        - next/... imports
        - App Router file structure (app/page.tsx, etc.)
        - Server Actions
        - API routes
        """
        # Check for Next.js directives
        if re.search(r"['\"]use (client|server)['\"]", file_content):
            return True

        # Check for Next.js imports
        if re.search(r"from\s+['\"]next/", file_content):
            return True

        # Check file structure
        if '/app/' in file_path and any(x in file_path for x in ['page.', 'layout.', 'route.', 'loading.', 'error.']):
            return True

        # Check for Server Actions
        if re.search(r"['\"]use server['\"]", file_content):
            return True

        return False

    def extract(self, file_content: str, file_path: str, root_dir: str) -> Dict[str, Any]:
        """
        Extract Next.js-specific data from file

        Returns:
            {
                "pages": [list of page components],
                "layouts": [list of layout components],
                "serverActions": [list of Server Actions],
                "apiRoutes": [list of API routes],
                "serverComponents": [list of Server Components],
                "clientComponents": [list of Client Components]
            }
        """
        rel_path = os.path.relpath(file_path, root_dir)

        results = {
            "pages": [],
            "layouts": [],
            "serverActions": [],
            "apiRoutes": [],
            "serverComponents": [],
            "clientComponents": [],
            "middleware": []
        }

        # Determine file type from path
        file_type = self._determine_file_type(file_path)

        # Extract based on file type
        if file_type == "page":
            pages = self._extract_page(file_content, rel_path)
            results["pages"].extend(pages)
        elif file_type == "layout":
            layouts = self._extract_layout(file_content, rel_path)
            results["layouts"].extend(layouts)
        elif file_type == "route":
            api_routes = self._extract_api_route(file_content, rel_path)
            results["apiRoutes"].extend(api_routes)
        elif file_type == "middleware":
            middleware = self._extract_middleware(file_content, rel_path)
            results["middleware"].extend(middleware)

        # Extract Server Actions (can be in any file)
        server_actions = self._extract_server_actions(file_content, rel_path)
        results["serverActions"].extend(server_actions)

        # Determine if Server or Client Component
        if self._is_client_component(file_content):
            components = self._extract_client_components(file_content, rel_path)
            results["clientComponents"].extend(components)
        else:
            components = self._extract_server_components(file_content, rel_path)
            results["serverComponents"].extend(components)

        return results

    def _determine_file_type(self, file_path: str) -> str:
        """Determine Next.js file type from path"""
        if 'page.' in os.path.basename(file_path):
            return "page"
        elif 'layout.' in os.path.basename(file_path):
            return "layout"
        elif 'route.' in os.path.basename(file_path):
            return "route"
        elif 'middleware.' in os.path.basename(file_path):
            return "middleware"
        elif 'loading.' in os.path.basename(file_path):
            return "loading"
        elif 'error.' in os.path.basename(file_path):
            return "error"
        elif 'not-found.' in os.path.basename(file_path):
            return "not-found"
        return "component"

    def _is_client_component(self, content: str) -> bool:
        """Check if file has 'use client' directive"""
        # Check first few lines for 'use client'
        first_lines = '\n'.join(content.split('\n')[:5])
        return bool(re.search(r"['\"]use client['\"]", first_lines))

    def _extract_page(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract page component"""
        pages = []

        # Extract route from file path
        # app/dashboard/page.tsx -> /dashboard
        # app/page.tsx -> /
        route = self._extract_route_from_path(file_path)

        # Find default export function
        export_pattern = r'export\s+default\s+(?:async\s+)?function\s+(\w+)'
        match = re.search(export_pattern, content)

        if match:
            component_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            is_async = 'async' in match.group(0)

            page = {
                "id": f"{file_path}:Page",
                "name": component_name,
                "route": route,
                "file": file_path,
                "line": line_num,
                "isAsync": is_async,
                "isServerComponent": not self._is_client_component(content),
                "params": self._extract_params(file_path),
                "searchParams": 'searchParams' in content
            }
            pages.append(page)

        return pages

    def _extract_layout(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract layout component"""
        layouts = []

        route = self._extract_route_from_path(file_path)

        # Find default export function
        export_pattern = r'export\s+default\s+function\s+(\w+)'
        match = re.search(export_pattern, content)

        if match:
            component_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            layout = {
                "id": f"{file_path}:Layout",
                "name": component_name,
                "route": route,
                "file": file_path,
                "line": line_num,
                "hasMetadata": 'export const metadata' in content or 'export async function generateMetadata' in content
            }
            layouts.append(layout)

        return layouts

    def _extract_api_route(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract API route handlers (route.ts)"""
        api_routes = []

        route = self._extract_route_from_path(file_path)

        # HTTP methods in Next.js API routes
        methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']

        for method in methods:
            pattern = rf'export\s+async\s+function\s+{method}\s*\('
            match = re.search(pattern, content)

            if match:
                line_num = content[:match.start()].count('\n') + 1

                api_route = {
                    "id": f"{file_path}:{method}",
                    "method": method,
                    "route": route,
                    "file": file_path,
                    "line": line_num,
                    "isAsync": True
                }
                api_routes.append(api_route)

        return api_routes

    def _extract_server_actions(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract Server Actions"""
        actions = []

        # Check if file has 'use server' directive
        has_use_server = "'use server'" in content or '"use server"' in content

        if not has_use_server:
            return actions

        # Pattern: export async function actionName(formData: FormData) { ... }
        action_pattern = r'export\s+async\s+function\s+(\w+)\s*\('
        for match in re.finditer(action_pattern, content):
            action_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            action = {
                "id": f"{file_path}:{action_name}",
                "name": action_name,
                "file": file_path,
                "line": line_num,
                "type": "server_action"
            }
            actions.append(action)

        return actions

    def _extract_server_components(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract Server Components (default in App Router)"""
        components = []

        # Find async component functions (common in Server Components)
        async_pattern = r'export\s+default\s+async\s+function\s+(\w+)'
        for match in re.finditer(async_pattern, content):
            component_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            component = {
                "id": f"{file_path}:{component_name}",
                "name": component_name,
                "file": file_path,
                "line": line_num,
                "isAsync": True,
                "type": "server"
            }
            components.append(component)

        return components

    def _extract_client_components(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract Client Components ('use client')"""
        components = []

        # Find component exports
        export_pattern = r'export\s+(?:default\s+)?function\s+(\w+)'
        for match in re.finditer(export_pattern, content):
            component_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            # Check if it uses hooks (common in Client Components)
            uses_hooks = bool(re.search(r'use(State|Effect|Context|Reducer|Callback|Memo|Ref)', content))

            component = {
                "id": f"{file_path}:{component_name}",
                "name": component_name,
                "file": file_path,
                "line": line_num,
                "type": "client",
                "usesHooks": uses_hooks
            }
            components.append(component)

        return components

    def _extract_middleware(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract Next.js middleware"""
        middleware = []

        # Pattern: export function middleware(request: NextRequest) { ... }
        middleware_pattern = r'export\s+function\s+middleware\s*\('
        match = re.search(middleware_pattern, content)

        if match:
            line_num = content[:match.start()].count('\n') + 1

            # Extract matcher config if present
            matcher = self._extract_matcher(content)

            middleware.append({
                "id": f"{file_path}:middleware",
                "name": "middleware",
                "file": file_path,
                "line": line_num,
                "matcher": matcher
            })

        return middleware

    def _extract_route_from_path(self, file_path: str) -> str:
        """Extract route from file path"""
        # app/dashboard/settings/page.tsx -> /dashboard/settings
        # app/page.tsx -> /
        if '/app/' not in file_path:
            return "/"

        parts = file_path.split('/app/')[1].split('/')
        # Remove file name (page.tsx, layout.tsx, etc.)
        parts = [p for p in parts if not p.startswith('page.') and not p.startswith('layout.') and not p.startswith('route.')]

        # Handle dynamic routes [id] -> :id
        parts = [f":{p[1:-1]}" if p.startswith('[') and p.endswith(']') else p for p in parts]

        route = '/' + '/'.join(parts) if parts else '/'
        return route.rstrip('/')  or '/'

    def _extract_params(self, file_path: str) -> List[str]:
        """Extract dynamic route parameters from path"""
        params = []
        parts = file_path.split('/')
        for part in parts:
            if part.startswith('[') and part.endswith(']'):
                params.append(part[1:-1])
        return params

    def _extract_matcher(self, content: str) -> List[str]:
        """Extract middleware matcher configuration"""
        matcher_match = re.search(r'matcher\s*:\s*\[([^\]]+)\]', content)
        if matcher_match:
            values = matcher_match.group(1).split(',')
            return [v.strip().strip("'\"") for v in values]

        matcher_match = re.search(r"matcher\s*:\s*['\"]([^'\"]+)['\"]", content)
        if matcher_match:
            return [matcher_match.group(1)]

        return []
