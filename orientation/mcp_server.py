#!/usr/bin/env python3
"""
MCP Server for Orientation — Loads Commander conditioning + Beast AppMap.

Exposes one tool: `orient`
Call it at session start to get:
  - Commander orientation text (mode rules, signal vocabulary, failure modes)
  - Current project architecture map (endpoints, components, metadata)
"""

import json
import sys
import os
import logging
from pathlib import Path

# Server lives alongside main_v2.py and orientation.md
SERVER_DIR = Path(__file__).parent

# Set up logging to a file for debugging
log_file = SERVER_DIR / "mcp_server.log"
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(log_file, mode='a')]
)
logger = logging.getLogger(__name__)

# Make sibling modules importable
sys.path.insert(0, str(SERVER_DIR))


class OrientationServer:
    def __init__(self):
        self.name = "orientation"
        self.version = "1.0.0"
        self.orientation_path = SERVER_DIR / "orientation.md"

    def get_capabilities(self):
        return {
            "name": self.name,
            "version": self.version,
            "tools": [
                {
                    "name": "orient",
                    "description": (
                        "Load Commander orientation + current project architecture map. "
                        "Call this first when starting a session with Commander. "
                        "Returns the orientation.md content (mode rules, signal vocabulary, "
                        "failure modes) plus a Beast-generated AppMap of the project "
                        "(endpoints, components, metadata) split into overview + components sections."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project_path": {
                                "type": "string",
                                "description": (
                                    "Path to project directory. If omitted, defaults to the "
                                    "server's current working directory (typically the directory "
                                    "Claude Code was launched from)."
                                )
                            }
                        }
                    }
                }
            ]
        }

    def orient(self, project_path: str = None) -> str:
        """Load orientation text + generate appmap for the project. Returns markdown string."""
        try:
            # Clear gate state first — fresh instance inherits no halt or drift
            self._clear_gate_state()

            # Read orientation.md from server directory
            if not self.orientation_path.exists():
                return f"ERROR: orientation.md not found at {self.orientation_path}"
            orientation_text = self.orientation_path.read_text(encoding='utf-8')

            # Resolve project path
            if not project_path:
                project_path = os.getcwd()

            project_path = os.path.abspath(project_path)
            if not os.path.isdir(project_path):
                return (
                    f"{orientation_text}\n\n---\n\n"
                    f"# AppMap\n\n"
                    f"**ERROR:** Project path does not exist or is not a directory: `{project_path}`\n"
                )

            # Import Beast and generate appmap
            try:
                from main_v2 import generate_appmap
            except Exception as e:
                logger.error(f"Failed to import generate_appmap: {e}", exc_info=True)
                return (
                    f"{orientation_text}\n\n---\n\n"
                    f"# AppMap\n\n"
                    f"**ERROR:** Failed to import Beast: {e}\n"
                    f"**Project path:** `{project_path}`\n"
                )

            logger.info(f"Generating appmap for: {project_path}")
            try:
                appmap = generate_appmap(project_path)
            except Exception as e:
                logger.error(f"generate_appmap failed: {e}", exc_info=True)
                return (
                    f"{orientation_text}\n\n---\n\n"
                    f"# AppMap\n\n"
                    f"**ERROR:** AppMap generation failed: {e}\n"
                    f"**Project path:** `{project_path}`\n"
                )

            appmap_md = self._format_appmap_as_markdown(appmap, project_path)
            return f"{orientation_text}\n\n---\n\n{appmap_md}"
        except Exception as e:
            logger.error(f"orient() unexpected error: {e}", exc_info=True)
            return f"ERROR: {e}"

    def _clear_gate_state(self):
        """Reset gate enforcement state — fresh instance inherits no halt or drift."""
        gate_state_path = Path("C:/gate/gate-state.json")
        if not gate_state_path.exists():
            return
        try:
            with open(gate_state_path, "r") as f:
                state = json.load(f)
            state["halt_latch"] = False
            state["drift_halt"] = False
            state["drift_score"] = 0
            state["drift_signals"] = {}
            state["drift_block_count"] = 0
            with open(gate_state_path, "w") as f:
                json.dump(state, f)
            logger.info("Gate state cleared by orient(): halt_latch, drift_halt, drift_score, drift_signals, drift_block_count reset")
        except Exception as e:
            logger.error(f"Failed to clear gate state: {e}")

    def _format_appmap_as_markdown(self, appmap: dict, project_path: str) -> str:
        """Convert appmap dict to a markdown document."""
        lines = []

        # Header
        app_name = appmap.get("appName", "unknown")
        lines.append(f"# AppMap: {app_name}")
        lines.append("")
        lines.append(f"**Path:** `{project_path}`")
        lines.append(f"**Generated:** {appmap.get('generatedAt', 'unknown')}")
        lines.append(f"**Version:** {appmap.get('appMapVersion', 'unknown')}")

        base_url = appmap.get("baseUrl")
        if base_url:
            lines.append(f"**Base URL:** {base_url}")

        auth = appmap.get("auth", {}) or {}
        if auth.get("default") and auth.get("default") != "none":
            lines.append(f"**Auth:** {auth.get('default')}")

        metadata = appmap.get("metadata", {}) or {}
        if metadata:
            file_count = metadata.get("file_count", 0)
            langs = metadata.get("detected_languages", [])
            frameworks = metadata.get("detected_frameworks", [])
            libraries = metadata.get("detected_libraries", [])
            lines.append(f"**Files scanned:** {file_count}")
            if langs:
                lines.append(f"**Languages:** {', '.join(langs)}")
            if frameworks:
                lines.append(f"**Frameworks:** {', '.join(frameworks)}")
            if libraries:
                lines.append(f"**Libraries:** {', '.join(libraries)}")
        lines.append("")

        # Endpoints
        endpoints = appmap.get("endpoints", []) or []
        lines.append(f"## Endpoints ({len(endpoints)})")
        lines.append("")
        if endpoints:
            lines.append("| Method | Path | File | Line | Handler | Type |")
            lines.append("|--------|------|------|------|---------|------|")
            for ep in endpoints:
                method = ep.get("method", "")
                path = ep.get("path", "")
                file = ep.get("file", "")
                line = ep.get("line", "")
                handler = str(ep.get("handler", "")).replace("|", "\\|")
                htype = ep.get("handlerType", "")
                lines.append(f"| {method} | `{path}` | `{file}` | {line} | `{handler}` | {htype} |")
        else:
            lines.append("_(none)_")
        lines.append("")

        # React components
        react = appmap.get("react", {}) or {}
        components = react.get("components", []) or []
        lines.append(f"## React Components ({len(components)})")
        lines.append("")
        if components:
            lines.append("| Name | File | Line | Type | Hooks | Props |")
            lines.append("|------|------|------|------|-------|-------|")
            for comp in components:
                name = comp.get("name", "")
                file = comp.get("file", "")
                line = comp.get("line", "")
                ctype = comp.get("type", "")
                hooks_list = comp.get("hooks", []) or []
                hooks = ", ".join(hooks_list) if hooks_list else "—"
                props_obj = comp.get("props", {}) or {}
                props_sig = props_obj.get("signature", "") if isinstance(props_obj, dict) else ""
                if props_sig and props_sig != "null":
                    props_sig = str(props_sig).replace("\n", " ").replace("|", "\\|")
                    if len(props_sig) > 80:
                        props_sig = props_sig[:77] + "..."
                    props_display = f"`{props_sig}`"
                else:
                    props_display = "—"
                lines.append(f"| {name} | `{file}` | {line} | {ctype} | {hooks} | {props_display} |")
        else:
            lines.append("_(none)_")
        lines.append("")

        # Custom hooks
        custom_hooks = react.get("customHooks", []) or []
        if custom_hooks:
            lines.append(f"## Custom Hooks ({len(custom_hooks)})")
            lines.append("")
            for hook in custom_hooks:
                lines.append(f"- `{hook}`")
            lines.append("")

        # Global state
        global_state = react.get("globalState", []) or []
        if global_state:
            lines.append(f"## Global State ({len(global_state)})")
            lines.append("")
            for gs in global_state:
                lines.append(f"- `{gs}`")
            lines.append("")

        # Functions
        functions = appmap.get("functions", []) or []
        if functions:
            lines.append(f"## Functions ({len(functions)})")
            lines.append("")
            lines.append("| Name | File | Line |")
            lines.append("|------|------|------|")
            for fn in functions:
                name = fn.get("name", "")
                file = fn.get("file", "")
                line = fn.get("line", "")
                lines.append(f"| {name} | `{file}` | {line} |")
            lines.append("")

        # Classes
        classes = appmap.get("classes", []) or []
        if classes:
            lines.append(f"## Classes ({len(classes)})")
            lines.append("")
            lines.append("| Name | File | Line |")
            lines.append("|------|------|------|")
            for cls in classes:
                name = cls.get("name", "")
                file = cls.get("file", "")
                line = cls.get("line", "")
                lines.append(f"| {name} | `{file}` | {line} |")
            lines.append("")

        # Database
        database = appmap.get("database", {}) or {}
        models = database.get("models", []) if isinstance(database, dict) else []
        schemas = database.get("schemas", []) if isinstance(database, dict) else []
        if models or schemas:
            lines.append("## Database")
            lines.append("")
            if models:
                lines.append(f"### Models ({len(models)})")
                for model in models:
                    lines.append(f"- {model}")
                lines.append("")
            if schemas:
                lines.append(f"### Schemas ({len(schemas)})")
                for schema in schemas:
                    lines.append(f"- {schema}")
                lines.append("")

        # Flows
        flows = appmap.get("flows", []) or []
        if flows:
            lines.append(f"## Flows ({len(flows)})")
            lines.append("")
            for flow in flows:
                lines.append(f"- {flow}")
            lines.append("")

        # ChefScript
        cs = appmap.get("chefscript", {}) or {}
        if cs:
            lines.append("---")
            lines.append("")
            lines.append("# ChefScript Architecture")
            lines.append("")

            # Pages
            cs_pages = cs.get("pages", []) or []
            if cs_pages:
                lines.append(f"## Pages ({len(cs_pages)})")
                lines.append("")
                lines.append("| Name | Title | Type | Components | Data Bindings |")
                lines.append("|------|-------|------|------------|---------------|")
                for pg in cs_pages:
                    name = pg.get("name", "")
                    title = pg.get("title", "")
                    ptype = pg.get("pageType", "")
                    comps = ", ".join(pg.get("components", [])[:8])
                    if len(pg.get("components", [])) > 8:
                        comps += f" +{len(pg['components']) - 8}"
                    binds = ", ".join(pg.get("dataBindings", [])[:5])
                    if len(pg.get("dataBindings", [])) > 5:
                        binds += f" +{len(pg['dataBindings']) - 5}"
                    lines.append(f"| {name} | {title} | {ptype} | {comps} | {binds} |")
                lines.append("")

            # Component Registry
            cs_comps = cs.get("components", []) or []
            if cs_comps:
                # Group by group name
                groups = {}
                for c in cs_comps:
                    g = c.get("group", "") or "core"
                    groups.setdefault(g, []).append(c)

                lines.append(f"## Component Registry ({len(cs_comps)} components)")
                lines.append("")
                for group_name, comps in sorted(groups.items()):
                    lines.append(f"### {group_name} ({len(comps)})")
                    lines.append("")
                    names = [c["name"] for c in comps]
                    lines.append(", ".join(f"`{n}`" for n in names))
                    lines.append("")

            # Binary Schemas
            cs_schemas = cs.get("schemas", []) or []
            if cs_schemas:
                lines.append(f"## Binary Schemas ({len(cs_schemas)})")
                lines.append("")
                lines.append("| Collection | Binary | Fields |")
                lines.append("|------------|--------|--------|")
                for s in cs_schemas:
                    coll = s.get("collection", "")
                    bcoll = s.get("binaryCollection", "")
                    fields = ", ".join(f.get("name", "") for f in s.get("fields", []))
                    if len(fields) > 80:
                        fields = fields[:77] + "..."
                    lines.append(f"| {coll} | {bcoll} | {fields} |")
                lines.append("")

            # Routes — Pages
            rp = cs.get("routes_pages", []) or []
            if rp:
                lines.append(f"## Registered Pages ({len(rp)})")
                lines.append("")
                for r in rp:
                    lines.append(f"- `{r['name']}` ({r['file']}:{r['line']})")
                lines.append("")

            # Routes — Actions
            ra = cs.get("routes_actions", []) or []
            if ra:
                lines.append(f"## Registered Actions ({len(ra)})")
                lines.append("")
                for r in ra:
                    lines.append(f"- `{r['name']}` ({r['file']}:{r['line']})")
                lines.append("")

            # Subsystem Registrations
            subs = cs.get("subsystems", []) or []
            if subs:
                lines.append(f"## Subsystem Registrations ({len(subs)})")
                lines.append("")
                for s in subs:
                    lines.append(f"- `{s['name']}` ({s['file']}:{s['line']})")
                lines.append("")

        return "\n".join(lines)


def main():
    """Main stdio JSON-RPC server loop."""
    logger.info("Orientation MCP Server starting...")

    try:
        server = OrientationServer()
        logger.info("OrientationServer initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize server: {e}", exc_info=True)
        sys.exit(1)

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                logger.info("EOF received, shutting down")
                break

            line = line.strip()
            if not line:
                continue

            logger.debug(f"Received: {line}")

            try:
                request = json.loads(line)
            except json.JSONDecodeError as e:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {e}"}
                }
                print(json.dumps(error_response))
                sys.stdout.flush()
                continue

            request_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})

            logger.debug(f"Processing method: {method}")

            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "orientation",
                            "version": "1.0.0"
                        }
                    }
                }

            elif method == "tools/list":
                capabilities = server.get_capabilities()
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"tools": capabilities["tools"]}
                }

            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                logger.debug(f"Calling tool: {tool_name} with args: {arguments}")

                try:
                    if tool_name == "orient":
                        result = server.orient(**arguments)
                    else:
                        result = f"ERROR: Unknown tool: {tool_name}"

                    logger.debug("Tool call complete")

                    # Pass string result through as-is; serialize dicts to JSON
                    if isinstance(result, str):
                        text_content = result
                    else:
                        text_content = json.dumps(result, indent=2)

                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": text_content
                                }
                            ]
                        }
                    }
                except Exception as e:
                    logger.error(f"Tool execution error: {e}", exc_info=True)
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32603,
                            "message": f"Tool execution error: {str(e)}"
                        }
                    }

            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }

            response_str = json.dumps(response)
            logger.debug(f"Sending: {response_str}")
            print(response_str)
            sys.stdout.flush()

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }
            print(json.dumps(error_response))
            sys.stdout.flush()

    logger.info("Orientation MCP Server shutting down")


if __name__ == "__main__":
    os.environ['PYTHONUNBUFFERED'] = '1'
    main()
