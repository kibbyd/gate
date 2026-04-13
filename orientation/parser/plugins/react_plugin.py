"""
React Framework Plugin - Detects and extracts React components, hooks, and patterns
"""
import os
import re
from typing import Dict, List, Any
from parser.base_plugin import FrameworkPlugin, PluginMetadata


class ReactPlugin(FrameworkPlugin):
    """Detect and extract React components, hooks, contexts, etc."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="react",
            category="framework",
            language="javascript",
            file_extensions=[".jsx", ".tsx", ".js", ".ts"],
            package_indicators=["react", "react-dom"]
        )

    def detect(self, file_content: str, file_path: str) -> bool:
        """
        Returns True if file contains React code

        Checks for:
        - Import from 'react'
        - JSX syntax
        - React hooks (useState, useEffect, etc.)
        """
        # Check for React imports
        if re.search(r'from\s+[\'"]react[\'"]', file_content):
            return True

        # Check for JSX syntax (return statements with JSX)
        if re.search(r'return\s*\(?\s*<[A-Z]', file_content):
            return True

        # Check for React hooks
        if re.search(r'use[A-Z]\w+\s*\(', file_content):
            return True

        return False

    def extract(self, file_content: str, file_path: str, root_dir: str) -> Dict[str, Any]:
        """
        Extract React-specific data from file

        Returns:
            {
                "components": [list of component objects],
                "hooks": [list of custom hooks],
                "contexts": [list of context providers]
            }
        """
        rel_path = os.path.relpath(file_path, root_dir)

        results = {
            "components": [],
            "hooks": [],
            "contexts": []
        }

        # Extract components
        components = self._extract_components(file_content, rel_path)
        results["components"].extend(components)

        # Extract custom hooks
        hooks = self._extract_custom_hooks(file_content, rel_path)
        results["hooks"].extend(hooks)

        # Extract contexts
        contexts = self._extract_contexts(file_content, rel_path)
        results["contexts"].extend(contexts)

        return results

    def _extract_components(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract React component declarations"""
        components = []

        # Pattern 1: Function components (function ComponentName() { ... })
        func_pattern = r'(?:export\s+(?:default\s+)?)?function\s+([A-Z]\w+)\s*\([^)]*\)\s*\{'
        for match in re.finditer(func_pattern, content):
            comp_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            # Check if it returns JSX
            if self._returns_jsx(content, match.start()):
                component = {
                    "id": f"{file_path}:{comp_name}",
                    "name": comp_name,
                    "file": file_path,
                    "line": line_num,
                    "type": "function",
                    "isServerComponent": self._is_server_component(content, match.start()),
                    "hooks": self._extract_hooks_usage(content, match.start()),
                    "props": self._extract_props(content, match.start())
                }
                components.append(component)

        # Pattern 2: Arrow function components (const ComponentName = () => { ... })
        # Handles: const Comp = () =>, const Comp: React.FC = () =>, const Comp: React.FC<Props> = ({...}) =>
        arrow_pattern = r'(?:export\s+)?const\s+([A-Z]\w+)\s*(?::\s*[\w.<>]+)?\s*=\s*\([^=]*\)\s*=>'
        for match in re.finditer(arrow_pattern, content):
            comp_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            if self._returns_jsx(content, match.start()):
                component = {
                    "id": f"{file_path}:{comp_name}",
                    "name": comp_name,
                    "file": file_path,
                    "line": line_num,
                    "type": "arrow",
                    "isServerComponent": self._is_server_component(content, match.start()),
                    "hooks": self._extract_hooks_usage(content, match.start()),
                    "props": self._extract_props(content, match.start())
                }
                components.append(component)

        # Pattern 3: Class components (class ComponentName extends React.Component)
        class_pattern = r'class\s+([A-Z]\w+)\s+extends\s+(?:React\.)?Component'
        for match in re.finditer(class_pattern, content):
            comp_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            component = {
                "id": f"{file_path}:{comp_name}",
                "name": comp_name,
                "file": file_path,
                "line": line_num,
                "type": "class",
                "isServerComponent": False,  # Class components are always client
                "hooks": [],  # Class components don't use hooks
                "props": {}
            }
            components.append(component)

        return components

    def _extract_custom_hooks(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract custom React hooks (functions starting with 'use')"""
        hooks = []

        # Pattern: function useSomething() or const useSomething = () =>
        hook_pattern = r'(?:function|const)\s+(use[A-Z]\w+)'
        for match in re.finditer(hook_pattern, content):
            hook_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            hook = {
                "id": f"{file_path}:{hook_name}",
                "name": hook_name,
                "file": file_path,
                "line": line_num,
                "dependencies": self._extract_hooks_usage(content, match.start())
            }
            hooks.append(hook)

        return hooks

    def _extract_contexts(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract React Context providers"""
        contexts = []

        # Pattern: createContext or React.createContext
        context_pattern = r'(?:const|export\s+const)\s+(\w+Context)\s*=\s*(?:React\.)?createContext'
        for match in re.finditer(context_pattern, content):
            context_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            context = {
                "id": f"{file_path}:{context_name}",
                "name": context_name,
                "file": file_path,
                "line": line_num
            }
            contexts.append(context)

        return contexts

    def _returns_jsx(self, content: str, start_pos: int) -> bool:
        """Check if function/component returns JSX"""
        # Look for return statement with JSX (any element, not just components)
        remaining_content = content[start_pos:start_pos + 5000]  # Check next 5000 chars (larger components)
        # Match: return <div>, return (<div>, return\n<div>, etc.
        return bool(re.search(r'return\s*\(?[\s\n]*<[a-zA-Z]', remaining_content))

    def _is_server_component(self, content: str, start_pos: int) -> bool:
        """
        Check if this is a Next.js Server Component
        (no 'use client' directive at top of file)
        """
        # Check if 'use client' appears before component definition
        before_component = content[:start_pos]
        has_use_client = "'use client'" in before_component or '"use client"' in before_component
        return not has_use_client

    def _extract_hooks_usage(self, content: str, start_pos: int) -> List[str]:
        """Extract which React hooks are used in this component (built-in and custom)"""
        hooks = set()

        # Look in next 1500 chars after component start (increased to catch more hooks)
        remaining_content = content[start_pos:start_pos + 1500]

        # Find all hook calls (anything starting with 'use' followed by capital letter)
        hook_pattern = r'\b(use[A-Z]\w*)\s*\('
        for match in re.finditer(hook_pattern, remaining_content):
            hook_name = match.group(1)
            hooks.add(hook_name)

        return sorted(list(hooks))

    def _extract_props(self, content: str, start_pos: int) -> Dict[str, Any]:
        """Extract component props (simplified - could be enhanced with TypeScript parsing)"""
        # This is a simplified version - would need proper TS parser for full prop types
        # Look for props in function signature
        match = re.search(r'\(([^)]+)\)', content[start_pos:start_pos + 200])
        if match:
            params = match.group(1).strip()
            if params and params != '':
                return {"signature": params}
        return {}
