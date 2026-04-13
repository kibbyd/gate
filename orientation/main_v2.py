#!/usr/bin/env python3
"""
Beast v2 - Modular plugin-based codebase analyzer
"""
import argparse
import sys
import os
import json
from datetime import datetime

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'backslashreplace')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'backslashreplace')
    except:
        pass

from utils import load_template, save_json
from parser.plugin_manager import PluginManager
from parser.plugins import (
    ReactPlugin, ExpressPlugin, SequelizePlugin,
    MongoosePlugin, MaterialUIPlugin, NextJSPlugin,
    ChefScriptPlugin
)
from parser.plugins.python_plugin import PythonParser
from db_manager import BeastDB


def init_plugin_manager() -> PluginManager:
    """Initialize and register all available plugins"""
    manager = PluginManager()

    # Register language parsers
    manager.register_language_parser(PythonParser())

    # Register framework plugins
    manager.register_framework_plugin(ReactPlugin())
    manager.register_framework_plugin(ExpressPlugin())
    manager.register_framework_plugin(NextJSPlugin())
    manager.register_framework_plugin(ChefScriptPlugin())

    # Register library plugins
    manager.register_library_plugin(SequelizePlugin())
    manager.register_library_plugin(MongoosePlugin())
    manager.register_library_plugin(MaterialUIPlugin())

    return manager


def extract_component_source(file_path: str, line: int, comp_name: str) -> str:
    """Extract the full source code of a component from file"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        # Start from the component line
        start_idx = line - 1
        if start_idx >= len(lines):
            return ""

        # Find the component declaration and extract until end
        source_lines = []
        brace_count = 0
        paren_count = 0
        started = False

        for i in range(start_idx, min(start_idx + 500, len(lines))):
            line_content = lines[i]
            source_lines.append(line_content)

            # Count braces and parens to find the end
            for char in line_content:
                if char == '{':
                    brace_count += 1
                    started = True
                elif char == '}':
                    brace_count -= 1
                elif char == '(':
                    paren_count += 1
                elif char == ')':
                    paren_count -= 1

            # Component ends when braces balance out
            if started and brace_count == 0 and paren_count <= 0:
                break

        return ''.join(source_lines)
    except Exception:
        return ""


def _merge_chefscript(appmap: dict, results: dict):
    """Merge ChefScript plugin data into the appmap dict."""
    fw_data = results.get('framework_data', {}).get('chefscript', {})
    if not fw_data:
        return

    cs = {}

    if fw_data.get('pages'):
        cs['pages'] = fw_data['pages']
    if fw_data.get('components'):
        cs['components'] = fw_data['components']
    if fw_data.get('schemas'):
        cs['schemas'] = fw_data['schemas']
    if fw_data.get('routes_pages'):
        cs['routes_pages'] = fw_data['routes_pages']
    if fw_data.get('routes_actions'):
        cs['routes_actions'] = fw_data['routes_actions']
    if fw_data.get('subsystems'):
        cs['subsystems'] = fw_data['subsystems']

    if cs:
        appmap['chefscript'] = cs


def run_beast(project_dir: str, template_name: str = None, universal: bool = False, verbose: bool = True):
    """
    Run Beast analysis on project using template-driven plugin system or universal auto-detection

    Args:
        project_dir: Path to project directory
        template_name: Name of template to use (from database)
        universal: Use universal auto-detection mode (no template needed)
        verbose: Print progress messages
    """
    if verbose:
        print(f"\n{'='*60}")
        print(f"Beast v2 - Analyzing: {project_dir}")
        print(f"{'='*60}\n")

    # Initialize database and plugin manager
    db = BeastDB()
    manager = init_plugin_manager()

    # Determine which mode to use
    template_config = None

    # Default to universal mode (no template needed)
    if not template_name or universal:
        # Universal mode: auto-detect everything
        if verbose:
            print("🌍 Using Universal Scanner Mode (auto-detection)")
        results = manager.parse_project_universal(project_dir, verbose=verbose)
    else:
        # Template mode: use specified template
        template_config = db.get_template(template_name)
        if not template_config:
            print(f"ERROR: Template '{template_name}' not found")
            print(f"\nAvailable templates:")
            for t in db.get_all_templates():
                print(f"  - {t['name']}")
            db.close()
            sys.exit(1)

        if verbose:
            print(f"Using template: {template_config['name']}")

        # Parse project using plugin manager (template mode)
        results = manager.parse_project(project_dir, template_config, verbose=verbose)

    # Load AppMap template
    appmap_template = load_template()
    appmap_template['appName'] = os.path.basename(project_dir)
    appmap_template['generatedAt'] = datetime.now().isoformat()

    # Merge results
    appmap_template['functions'] = results.get('functions', [])
    appmap_template['endpoints'] = results.get('endpoints', [])
    appmap_template['flows'] = results.get('flows', [])
    appmap_template['metadata'] = results.get('metadata', {})

    # Add classes (Python)
    if results.get('classes'):
        appmap_template['classes'] = results['classes']

    # Add framework-specific data
    if results.get('components'):
        if 'react' not in appmap_template:
            appmap_template['react'] = {'components': [], 'customHooks': [], 'globalState': []}
        appmap_template['react']['components'] = results['components']

    # Add database models
    if results.get('models'):
        if 'database' not in appmap_template:
            appmap_template['database'] = {}
        appmap_template['database']['models'] = results['models']

    if results.get('schemas'):
        if 'database' not in appmap_template:
            appmap_template['database'] = {}
        appmap_template['database']['schemas'] = results['schemas']

    # Merge ChefScript-specific data
    _merge_chefscript(appmap_template, results)

    # Save AppMap
    output_path = os.path.join(project_dir, 'AppMap.json')
    save_json(appmap_template, output_path)

    # Record in recent projects
    if template_config:
        db.add_recent_project(project_dir, template_config['name'])
        db.update_template_usage(template_config['name'])
    else:
        # Universal mode - use scan mode as identifier
        db.add_recent_project(project_dir, "Universal Scanner")

    if verbose:
        print(f"\n{'='*60}")
        print(f"SUCCESS! AppMap.json created")
        print(f"{'='*60}")
        print(f"Location: {output_path}")
        print(f"Functions: {len(appmap_template['functions'])}")
        print(f"Classes: {len(appmap_template.get('classes', []))}")
        print(f"Endpoints: {len(appmap_template['endpoints'])}")
        print(f"Components: {len(results.get('components', []))}")
        print(f"Models: {len(results.get('models', [])) + len(results.get('schemas', []))}")
        print(f"{'='*60}\n")

    db.close()


def generate_appmap(project_dir: str, template_name: str = None, universal: bool = False) -> dict:
    """
    Generate AppMap dict for a project without writing to disk.
    Mirrors run_beast() but returns the dict for in-process use (MCP tool, etc).

    Args:
        project_dir: Path to project directory
        template_name: Name of template to use (from database)
        universal: Use universal auto-detection mode (no template needed)

    Returns:
        Dict containing the full appmap structure
    """
    db = BeastDB()
    manager = init_plugin_manager()

    try:
        template_config = None

        if not template_name or universal:
            results = manager.parse_project_universal(project_dir, verbose=False)
        else:
            template_config = db.get_template(template_name)
            if not template_config:
                raise ValueError(f"Template '{template_name}' not found")
            results = manager.parse_project(project_dir, template_config, verbose=False)

        appmap_template = load_template()
        appmap_template['appName'] = os.path.basename(project_dir)
        appmap_template['generatedAt'] = datetime.now().isoformat()

        appmap_template['functions'] = results.get('functions', [])
        appmap_template['endpoints'] = results.get('endpoints', [])
        appmap_template['flows'] = results.get('flows', [])
        appmap_template['metadata'] = results.get('metadata', {})

        if results.get('classes'):
            appmap_template['classes'] = results['classes']

        if results.get('components'):
            if 'react' not in appmap_template:
                appmap_template['react'] = {'components': [], 'customHooks': [], 'globalState': []}
            appmap_template['react']['components'] = results['components']

        if results.get('models'):
            if 'database' not in appmap_template:
                appmap_template['database'] = {}
            appmap_template['database']['models'] = results['models']

        if results.get('schemas'):
            if 'database' not in appmap_template:
                appmap_template['database'] = {}
            appmap_template['database']['schemas'] = results['schemas']

        # Merge ChefScript-specific data
        _merge_chefscript(appmap_template, results)

        return appmap_template
    finally:
        db.close()


def auto_detect_template(project_dir: str, db: BeastDB):
    """Auto-detect project type by checking for package.json or requirements.txt"""
    # Check for package.json
    package_json_path = os.path.join(project_dir, 'package.json')
    if os.path.exists(package_json_path):
        try:
            with open(package_json_path, 'r', encoding='utf-8') as f:
                package_data = json.load(f)

            deps = {**package_data.get('dependencies', {}), **package_data.get('devDependencies', {})}

            # Check for Next.js
            if 'next' in deps:
                return db.get_template("Next.js Fullstack")

            # Check for React + Express
            if 'react' in deps and 'express' in deps:
                return db.get_template("React + Express + MongoDB")

            # Check for just Express
            if 'express' in deps:
                return db.get_template("Express API + Sequelize")

            # Fallback to React if react is present
            if 'react' in deps:
                return db.get_template("React + Express + MongoDB")

        except Exception as e:
            print(f"Warning: Could not parse package.json: {e}")

    # Check for requirements.txt (Python)
    requirements_path = os.path.join(project_dir, 'requirements.txt')
    if os.path.exists(requirements_path):
        with open(requirements_path, 'r', encoding='utf-8') as f:
            reqs = f.read().lower()

        # Check for tkinter (desktop)
        if 'tkinter' in reqs or os.path.exists(os.path.join(project_dir, 'main.py')):
            return db.get_template("Python Desktop (Tkinter)")

    return None


def list_templates():
    """List all available templates"""
    db = BeastDB()
    templates = db.get_all_templates()

    print("\n" + "="*60)
    print("Available Templates")
    print("="*60 + "\n")

    presets = [t for t in templates if t['is_preset']]
    custom = [t for t in templates if not t['is_preset']]

    if presets:
        print("PRESETS:")
        for t in presets:
            print(f"  {t['name']}")
            print(f"    {t['description']}")
            print(f"    Frameworks: {', '.join(t['frameworks'])}")
            print()

    if custom:
        print("CUSTOM:")
        for t in custom:
            print(f"  {t['name']}")
            print(f"    Frameworks: {', '.join(t['frameworks'])}")
            print()

    db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Beast v2: Universal codebase analyzer with auto-detection",
        epilog="By default, Beast uses universal auto-detection mode. Use --template for template-based analysis."
    )
    parser.add_argument("project", nargs="?", help="Path to project directory")
    parser.add_argument("--template", "-t", help="Template name to use (disables universal mode, see --list-templates)")
    parser.add_argument("--universal", "-u", action="store_true", help="Force universal scanner mode (default)")
    parser.add_argument("--list-templates", action="store_true", help="List available templates")
    parser.add_argument("--gui", action="store_true", help="Launch GUI")
    parser.add_argument("--web", action="store_true", help="Launch web GUI")

    args = parser.parse_args()

    # List templates
    if args.list_templates:
        list_templates()
        sys.exit(0)

    # Launch GUI
    if args.gui:
        print("GUI mode coming soon - use templates_cli.py to manage templates")
        sys.exit(0)

    if args.web:
        print("Web GUI mode coming soon")
        sys.exit(0)

    # CLI mode
    if not args.project:
        print("Error: Project directory required")
        print("Usage: python main_v2.py <project_dir>              # Universal auto-detection")
        print("       python main_v2.py <project_dir> --template <name>  # Template mode")
        print("       python main_v2.py --list-templates")
        sys.exit(1)

    run_beast(args.project, template_name=args.template, universal=args.universal, verbose=True)
