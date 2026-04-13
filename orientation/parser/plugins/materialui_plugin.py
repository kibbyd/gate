"""
Material-UI Library Plugin - Detects and extracts Material-UI component usage and theming
"""
import os
import re
from typing import Dict, List, Any
from parser.base_plugin import LibraryPlugin, PluginMetadata


class MaterialUIPlugin(LibraryPlugin):
    """Detect and extract Material-UI component usage, themes, and patterns"""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="material-ui",
            category="library",
            language="javascript",
            file_extensions=[".jsx", ".tsx", ".js", ".ts"],
            package_indicators=["@mui/material", "@material-ui/core"]
        )

    def detect(self, file_content: str, file_path: str) -> bool:
        """
        Returns True if file uses Material-UI

        Checks for:
        - import from '@mui/material' or '@material-ui/core'
        - MUI component usage
        - Theme provider
        """
        # Check for MUI imports
        if re.search(r"from\s+['\"]@mui/material", file_content):
            return True
        if re.search(r"from\s+['\"]@material-ui/core", file_content):
            return True
        if re.search(r"from\s+['\"]@mui/icons-material", file_content):
            return True

        # Check for common MUI components
        mui_components = ['Button', 'TextField', 'Box', 'Grid', 'Typography', 'AppBar', 'Dialog']
        for comp in mui_components:
            if re.search(rf'<{comp}\b', file_content):
                return True

        return False

    def extract(self, file_content: str, file_path: str, root_dir: str) -> Dict[str, Any]:
        """
        Extract Material-UI-specific data from file

        Returns:
            {
                "components": [list of MUI components used],
                "themes": [list of theme configurations],
                "sx_props": [list of sx prop usage],
                "styled_components": [list of styled() components]
            }
        """
        rel_path = os.path.relpath(file_path, root_dir)

        results = {
            "components": [],
            "themes": [],
            "sx_props": [],
            "styled_components": []
        }

        # Extract component usage
        components = self._extract_component_usage(file_content, rel_path)
        results["components"].extend(components)

        # Extract theme configurations
        themes = self._extract_themes(file_content, rel_path)
        results["themes"].extend(themes)

        # Extract sx prop usage
        sx_usage = self._extract_sx_usage(file_content, rel_path)
        results["sx_props"].extend(sx_usage)

        # Extract styled components
        styled = self._extract_styled_components(file_content, rel_path)
        results["styled_components"].extend(styled)

        return results

    def _extract_component_usage(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract which MUI components are used"""
        components_used = {}

        # Extract imports
        # Pattern: import { Button, TextField } from '@mui/material'
        import_pattern = r"import\s+\{([^}]+)\}\s+from\s+['\"]@mui/material['\"]"
        for match in re.finditer(import_pattern, content):
            imports = match.group(1).split(',')
            line_num = content[:match.start()].count('\n') + 1

            for comp in imports:
                comp_name = comp.strip()
                if comp_name and comp_name not in components_used:
                    components_used[comp_name] = {
                        "id": f"{file_path}:{comp_name}",
                        "component": comp_name,
                        "file": file_path,
                        "importLine": line_num,
                        "usageCount": 0,
                        "usageLines": []
                    }

        # Count actual usage in JSX
        for comp_name in components_used.keys():
            usage_pattern = rf'<{comp_name}\b'
            for match in re.finditer(usage_pattern, content):
                line_num = content[:match.start()].count('\n') + 1
                components_used[comp_name]["usageCount"] += 1
                if line_num not in components_used[comp_name]["usageLines"]:
                    components_used[comp_name]["usageLines"].append(line_num)

        return list(components_used.values())

    def _extract_themes(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract theme configurations"""
        themes = []

        # Pattern: createTheme({ ... })
        theme_pattern = r'createTheme\s*\(\s*\{'
        for match in re.finditer(theme_pattern, content):
            line_num = content[:match.start()].count('\n') + 1

            # Extract theme config
            theme_block = self._extract_block(content, match.end() - 1)

            # Extract theme properties
            theme_config = {
                "id": f"{file_path}:theme:{line_num}",
                "file": file_path,
                "line": line_num,
                "palette": self._extract_palette(theme_block),
                "typography": self._extract_typography(theme_block),
                "spacing": self._extract_spacing(theme_block),
                "breakpoints": self._extract_breakpoints(theme_block)
            }
            themes.append(theme_config)

        # Pattern: ThemeProvider
        provider_pattern = r'<ThemeProvider\s+theme='
        for match in re.finditer(provider_pattern, content):
            line_num = content[:match.start()].count('\n') + 1

            if not any(t['line'] == line_num for t in themes):
                themes.append({
                    "id": f"{file_path}:theme_provider:{line_num}",
                    "file": file_path,
                    "line": line_num,
                    "type": "provider"
                })

        return themes

    def _extract_sx_usage(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract sx prop usage (MUI's inline styling system)"""
        sx_usage = []

        # Pattern: sx={{ ... }} or sx={...}
        sx_pattern = r'sx\s*=\s*\{\{'
        for match in re.finditer(sx_pattern, content):
            line_num = content[:match.start()].count('\n') + 1

            # Find the component this sx belongs to
            component_match = re.search(r'<(\w+)', content[max(0, match.start()-50):match.start()])
            component_name = component_match.group(1) if component_match else "unknown"

            sx_usage.append({
                "id": f"{file_path}:sx:{line_num}",
                "file": file_path,
                "line": line_num,
                "component": component_name
            })

        return sx_usage

    def _extract_styled_components(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract styled() component definitions"""
        styled_components = []

        # Pattern: const StyledComponent = styled(Component)(...)
        styled_pattern = r'const\s+(\w+)\s*=\s*styled\((\w+)\)'
        for match in re.finditer(styled_pattern, content):
            component_name = match.group(1)
            base_component = match.group(2)
            line_num = content[:match.start()].count('\n') + 1

            styled_components.append({
                "id": f"{file_path}:{component_name}",
                "name": component_name,
                "baseComponent": base_component,
                "file": file_path,
                "line": line_num
            })

        return styled_components

    def _extract_block(self, content: str, start: int) -> str:
        """Extract a code block starting from position"""
        open_braces = 0
        i = start
        while i < len(content):
            if content[i] == '{':
                open_braces += 1
            elif content[i] == '}':
                open_braces -= 1
                if open_braces == 0:
                    return content[start:i+1]
            i += 1
        return content[start:start+500]

    def _extract_palette(self, theme_block: str) -> Dict[str, Any]:
        """Extract palette configuration"""
        palette = {}

        # Check for mode
        if 'mode:' in theme_block:
            mode_match = re.search(r"mode\s*:\s*['\"](\w+)['\"]", theme_block)
            if mode_match:
                palette['mode'] = mode_match.group(1)

        # Extract primary color
        primary_match = re.search(r"primary\s*:\s*\{[^}]*main\s*:\s*['\"]([^'\"]+)['\"]", theme_block)
        if primary_match:
            palette['primary'] = primary_match.group(1)

        # Extract secondary color
        secondary_match = re.search(r"secondary\s*:\s*\{[^}]*main\s*:\s*['\"]([^'\"]+)['\"]", theme_block)
        if secondary_match:
            palette['secondary'] = secondary_match.group(1)

        return palette if palette else None

    def _extract_typography(self, theme_block: str) -> Dict[str, Any]:
        """Extract typography configuration"""
        typography = {}

        # Extract font family
        font_match = re.search(r"fontFamily\s*:\s*['\"]([^'\"]+)['\"]", theme_block)
        if font_match:
            typography['fontFamily'] = font_match.group(1)

        return typography if typography else None

    def _extract_spacing(self, theme_block: str) -> Any:
        """Extract spacing configuration"""
        spacing_match = re.search(r"spacing\s*:\s*(\d+)", theme_block)
        if spacing_match:
            return int(spacing_match.group(1))
        return None

    def _extract_breakpoints(self, theme_block: str) -> Dict[str, Any]:
        """Extract breakpoints configuration"""
        # Simplified - could be enhanced
        if 'breakpoints:' in theme_block:
            return {"custom": True}
        return None
