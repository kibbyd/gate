"""
ChefScript Plugin — Detects and extracts CyberLab/ChefScript architecture.

Extracts:
  - Pages (JSON templates): title, components used, data bindings
  - Component registry: e.Register() calls from engine/components*.go
  - Binary schemas: collection definitions from schemas/binary/*.json
  - Routes: RegisterPage/RegisterAction calls from app.go
  - Subsystem registrations: Register*Components, Register* calls
"""
import os
import re
import json
from typing import Dict, List, Any
from parser.base_plugin import FrameworkPlugin, PluginMetadata


class ChefScriptPlugin(FrameworkPlugin):
    """Detect and extract ChefScript page templates, components, schemas, and routes."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="chefscript",
            category="framework",
            language="go",
            file_extensions=[".json", ".go"],
            package_indicators=["chefscript"]
        )

    def detect(self, file_content: str, file_path: str) -> bool:
        """Returns True if file is part of a ChefScript project."""
        # Page JSON templates live under pages/
        if file_path.replace("\\", "/").endswith(".json") and "/pages/" in file_path.replace("\\", "/"):
            return True
        # Component registry files
        if os.path.basename(file_path).startswith("components") and file_path.endswith(".go"):
            return True
        # Binary schema definitions
        if "/schemas/binary/" in file_path.replace("\\", "/") and file_path.endswith(".json"):
            return True
        # App bootstrap
        if os.path.basename(file_path) == "app.go":
            return True
        return False

    def extract(self, file_content: str, file_path: str, root_dir: str) -> Dict[str, Any]:
        """Route to the right extractor based on file type/location."""
        norm = file_path.replace("\\", "/")
        rel = os.path.relpath(file_path, root_dir).replace("\\", "/")

        if "/pages/" in norm and norm.endswith(".json"):
            return self._extract_page(file_content, rel)

        if os.path.basename(file_path).startswith("components") and norm.endswith(".go"):
            return self._extract_components(file_content, rel)

        if "/schemas/binary/" in norm and norm.endswith(".json"):
            return self._extract_schema(file_content, rel)

        if os.path.basename(file_path) == "app.go":
            return self._extract_routes(file_content, rel)

        return {}

    # ── Pages ──────────────────────────────────────────────────────────

    def _extract_page(self, content: str, rel_path: str) -> Dict[str, Any]:
        """Extract page metadata and component usage from a ChefScript JSON template."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return {}

        title = data.get("title", "")
        theme = data.get("theme", "")
        page_type = data.get("pageType", "")
        page_name = os.path.splitext(os.path.basename(rel_path))[0]

        # Walk the body tree to find component tags and data bindings
        components_used = set()
        bindings = set()
        self._walk_body(data.get("body", []), components_used, bindings)

        page = {
            "name": page_name,
            "title": title,
            "file": rel_path,
            "theme": theme,
            "pageType": page_type,
            "components": sorted(components_used),
            "dataBindings": sorted(bindings),
        }
        return {"pages": [page]}

    def _walk_body(self, node, components: set, bindings: set):
        """Recursively walk a ChefScript body array, collecting component names and {{}} bindings."""
        if not isinstance(node, list):
            return
        # A ChefScript element is ["tag", {props}, ...children]
        if len(node) >= 1 and isinstance(node[0], str):
            tag = node[0]
            # Standard HTML tags we skip — only collect custom components
            if tag not in {"div", "span", "p", "h1", "h2", "h3", "h4", "h5", "h6",
                           "a", "ul", "ol", "li", "img", "br", "hr", "b", "i", "em",
                           "strong", "small", "pre", "label", "style", "script"}:
                components.add(tag)

            # Scan props for data bindings
            if len(node) >= 2 and isinstance(node[1], dict):
                for v in node[1].values():
                    if isinstance(v, str):
                        for m in re.finditer(r"\{\{(.+?)\}\}", v):
                            bindings.add(m.group(1).strip())

            # Recurse into children (elements after tag and optional props dict)
            start = 2 if (len(node) >= 2 and isinstance(node[1], dict)) else 1
            for child in node[start:]:
                self._walk_body(child, components, bindings)
        else:
            # Could be a bare array of children
            for child in node:
                self._walk_body(child, components, bindings)

    # ── Component Registry ─────────────────────────────────────────────

    def _extract_components(self, content: str, rel_path: str) -> Dict[str, Any]:
        """Extract e.Register("name", ...) calls from engine/components*.go files."""
        components = []
        # Match: e.Register("component-name", ComponentFunc(renderFuncName))
        for m in re.finditer(r'e\.Register\(\s*"([^"]+)"\s*,\s*ComponentFunc\((\w+)\)', content):
            line_num = content[:m.start()].count("\n") + 1
            components.append({
                "name": m.group(1),
                "renderFunc": m.group(2),
                "file": rel_path,
                "line": line_num,
            })

        # Also capture the Register*Components function name for subsystem grouping
        group_name = None
        gm = re.search(r'func\s+(Register\w*Components?)\s*\(', content)
        if gm:
            group_name = gm.group(1)

        if components:
            for c in components:
                c["group"] = group_name or ""
            return {"components": components}
        return {}

    # ── Binary Schemas ─────────────────────────────────────────────────

    def _extract_schema(self, content: str, rel_path: str) -> Dict[str, Any]:
        """Extract binary schema definitions from schemas/binary/*.json."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return {}

        collection = data.get("collection", "")
        if not collection:
            return {}

        fields = []
        for f in data.get("fields", []):
            field = {
                "name": f.get("name", ""),
                "type": f.get("type", ""),
            }
            if f.get("index"):
                field["index"] = True
            if f.get("dynamic") is False and f.get("values"):
                field["values"] = f["values"]
            fields.append(field)

        schema = {
            "collection": collection,
            "binaryCollection": data.get("binaryCollection", ""),
            "file": rel_path,
            "fields": fields,
        }
        return {"schemas": [schema]}

    # ── Routes (app.go) ────────────────────────────────────────────────

    def _extract_routes(self, content: str, rel_path: str) -> Dict[str, Any]:
        """Extract RegisterPage and RegisterAction calls from app.go."""
        pages = []
        actions = []
        subsystems = []

        # RegisterPage("name", ...)
        for m in re.finditer(r'engine\.RegisterPage\(\s*"([^"]+)"', content):
            line_num = content[:m.start()].count("\n") + 1
            pages.append({
                "name": m.group(1),
                "file": rel_path,
                "line": line_num,
            })

        # RegisterAction("name", ...)
        for m in re.finditer(r'engine\.RegisterAction\(\s*"([^"]+)"', content):
            line_num = content[:m.start()].count("\n") + 1
            actions.append({
                "name": m.group(1),
                "file": rel_path,
                "line": line_num,
            })

        # Register*Components(e) and Register*() subsystem init calls
        for m in re.finditer(r'engine\.(Register\w+)\(', content):
            name = m.group(1)
            # Skip the ones already captured above
            if name in ("RegisterPage", "RegisterAction"):
                continue
            line_num = content[:m.start()].count("\n") + 1
            subsystems.append({
                "name": name,
                "file": rel_path,
                "line": line_num,
            })

        result = {}
        if pages:
            result["routes_pages"] = pages
        if actions:
            result["routes_actions"] = actions
        if subsystems:
            result["subsystems"] = subsystems
        return result
