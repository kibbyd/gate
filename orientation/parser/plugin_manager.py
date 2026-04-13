"""
Plugin Manager - Orchestrates loading and running parser plugins based on project template
"""
import os
from typing import Dict, List, Any, Optional
from parser.base_plugin import BasePlugin, FrameworkPlugin, LibraryPlugin, LanguageParser
from scanner import UniversalScanner


class PluginManager:
    """
    Manages loading and executing parser plugins based on project configuration
    """

    def __init__(self):
        self.language_parsers: Dict[str, LanguageParser] = {}
        self.framework_plugins: Dict[str, FrameworkPlugin] = {}
        self.library_plugins: Dict[str, LibraryPlugin] = {}

    def register_language_parser(self, parser: LanguageParser):
        """Register a language parser (Python, JavaScript, Java)"""
        self.language_parsers[parser.language] = parser

    def register_framework_plugin(self, plugin: FrameworkPlugin):
        """Register a framework plugin (React, Express, Flask, etc.)"""
        self.framework_plugins[plugin.metadata.name] = plugin

    def register_library_plugin(self, plugin: LibraryPlugin):
        """Register a library plugin (Material-UI, Sequelize, etc.)"""
        self.library_plugins[plugin.metadata.name] = plugin

    def load_plugins_for_template(self, template: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Load plugins based on template configuration

        Args:
            template: Template dict from database with keys:
                      languages, frameworks, libraries, databases

        Returns:
            Dict with loaded plugin names by category
        """
        loaded = {
            "languages": [],
            "frameworks": [],
            "libraries": []
        }

        # Load language parsers
        for lang in template.get('languages', []):
            if lang in self.language_parsers:
                loaded['languages'].append(lang)
            else:
                print(f"   WARNING: Language parser '{lang}' not available")

        # Load framework plugins
        for fw in template.get('frameworks', []):
            if fw in self.framework_plugins:
                loaded['frameworks'].append(fw)
            else:
                print(f"   WARNING: Framework plugin '{fw}' not available")

        # Load library plugins
        for lib in template.get('libraries', []):
            if lib in self.library_plugins:
                loaded['libraries'].append(lib)
            else:
                print(f"   WARNING: Library plugin '{lib}' not available")

        return loaded

    def parse_project(self, root_dir: str, template: Dict[str, Any], verbose: bool = True) -> Dict[str, Any]:
        """
        Parse entire project using template-specified plugins

        Args:
            root_dir: Project root directory
            template: Template configuration from database
            verbose: Print progress

        Returns:
            Combined results from all plugins
        """
        results = {
            "functions": [],
            "endpoints": [],
            "components": [],
            "models": [],
            "schemas": [],
            "flows": [],
            "metadata": {
                "template_used": template.get('name'),
                "languages": template.get('languages', []),
                "frameworks": template.get('frameworks', []),
                "libraries": template.get('libraries', [])
            }
        }

        if verbose:
            print(f"\n📦 Using template: {template.get('name')}")
            print(f"   Languages: {', '.join(template.get('languages', []))}")
            print(f"   Frameworks: {', '.join(template.get('frameworks', []))}")
            if template.get('libraries'):
                print(f"   Libraries: {', '.join(template.get('libraries', []))}")
            print()

        loaded = self.load_plugins_for_template(template)

        # Step 1: Run language parsers first (base layer)
        for lang in loaded['languages']:
            parser = self.language_parsers[lang]
            if verbose:
                print(f"🔍 Running {lang.upper()} parser...")

            lang_results = parser.parse_directory(root_dir, verbose=verbose)

            # Merge language results
            results['functions'].extend(lang_results.get('functions', []))
            results['endpoints'].extend(lang_results.get('endpoints', []))

        # Step 2: Run framework plugins (architecture layer)
        framework_data = {}
        for fw in loaded['frameworks']:
            plugin = self.framework_plugins[fw]
            if verbose:
                print(f"\n🔧 Running {fw.upper()} framework detector...")

            fw_data = self._run_plugin_on_directory(plugin, root_dir, verbose)
            framework_data[fw] = fw_data

            # Merge framework-specific results
            if 'components' in fw_data:
                results['components'].extend(fw_data['components'])
            if 'endpoints' in fw_data:
                results['endpoints'].extend(fw_data['endpoints'])
            if 'routes' in fw_data:
                results['endpoints'].extend(fw_data['routes'])

        # Step 3: Run library plugins (enhancement layer)
        library_data = {}
        for lib in loaded['libraries']:
            plugin = self.library_plugins[lib]
            if verbose:
                print(f"\n📚 Running {lib.upper()} library extractor...")

            lib_data = self._run_plugin_on_directory(plugin, root_dir, verbose)
            library_data[lib] = lib_data

            # Merge library-specific results
            if 'models' in lib_data:
                results['models'].extend(lib_data['models'])
            if 'schemas' in lib_data:
                results['schemas'].extend(lib_data['schemas'])

        # Store framework and library specific data
        results['framework_data'] = framework_data
        results['library_data'] = library_data

        if verbose:
            print(f"\n{'='*60}")
            print(f"✓ Parsing complete!")
            print(f"   Functions: {len(results['functions'])}")
            print(f"   Endpoints: {len(results['endpoints'])}")
            print(f"   Components: {len(results['components'])}")
            print(f"   Models: {len(results['models'])}")
            print(f"{'='*60}\n")

        return results

    def parse_project_universal(self, root_dir: str, verbose: bool = True) -> Dict[str, Any]:
        """
        Parse project using universal auto-detection (no template needed).

        Args:
            root_dir: Project root directory
            verbose: Print progress

        Returns:
            Combined results from all plugins, same format as parse_project()
        """
        if verbose:
            print(f"\n🔍 Universal Scanner Mode - Auto-detecting project structure...")

        # Step 1: Scan directory and detect everything
        scanner = UniversalScanner(verbose=verbose)
        scan_results = scanner.scan_directory(root_dir)

        detected_languages = scan_results['detected_languages']
        detected_frameworks = scan_results['detected_frameworks']
        detected_libraries = scan_results['detected_libraries']

        # Initialize results
        results = {
            "functions": [],
            "classes": [],
            "endpoints": [],
            "components": [],
            "models": [],
            "schemas": [],
            "flows": [],
            "metadata": {
                "scan_mode": "universal",
                "detected_languages": detected_languages,
                "detected_frameworks": detected_frameworks,
                "detected_libraries": detected_libraries,
                "file_count": scan_results['file_count'],
            }
        }

        # Check for ChefScript fingerprint: engine/engine.go + pages/*.json
        is_chefscript = (
            os.path.isfile(os.path.join(root_dir, 'engine', 'engine.go'))
            and any(f.replace('\\', '/').startswith('pages/') and f.endswith('.json')
                    for f in scan_results['all_files'])
        )

        if is_chefscript:
            if 'chefscript' not in detected_frameworks:
                detected_frameworks.append('chefscript')
            results['metadata']['detected_frameworks'] = detected_frameworks
            results['metadata']['primary_framework'] = 'chefscript'

        if verbose:
            print(f"\n{'='*60}")
            print(f"Auto-detected Configuration:")
            print(f"   Languages: {', '.join(detected_languages) if detected_languages else 'none'}")
            print(f"   Frameworks: {', '.join(detected_frameworks) if detected_frameworks else 'none'}")
            if is_chefscript:
                print(f"   Primary: ChefScript (skipping generic language parsers)")
            if detected_libraries:
                print(f"   Libraries: {', '.join(detected_libraries)}")
            print(f"{'='*60}\n")

        # Step 2: Run language parsers — skip if ChefScript is primary
        if not is_chefscript:
            for lang in detected_languages:
                if lang in self.language_parsers:
                    parser = self.language_parsers[lang]
                    if verbose:
                        print(f"🔍 Running {lang.upper()} parser...")

                    lang_results = parser.parse_directory(root_dir, verbose=verbose)

                    # Merge language results
                    results['functions'].extend(lang_results.get('functions', []))
                    results['classes'].extend(lang_results.get('classes', []))
                    results['endpoints'].extend(lang_results.get('endpoints', []))
                else:
                    if verbose:
                        print(f"   ⚠️  No parser available for {lang}")

        # Step 3: Run framework plugins for detected frameworks
        framework_data = {}
        for fw in detected_frameworks:
            if fw in self.framework_plugins:
                plugin = self.framework_plugins[fw]
                if verbose:
                    print(f"\n🔧 Running {fw.upper()} framework detector...")

                fw_data = self._run_plugin_on_directory(plugin, root_dir, verbose)
                framework_data[fw] = fw_data

                # Merge framework-specific results
                if 'components' in fw_data:
                    results['components'].extend(fw_data['components'])
                if 'endpoints' in fw_data:
                    results['endpoints'].extend(fw_data['endpoints'])
                if 'routes' in fw_data:
                    results['endpoints'].extend(fw_data['routes'])
            else:
                if verbose:
                    print(f"   ⚠️  No plugin available for {fw}")

        # Step 4: Run library plugins for detected libraries
        library_data = {}
        for lib in detected_libraries:
            if lib in self.library_plugins:
                plugin = self.library_plugins[lib]
                if verbose:
                    print(f"\n📚 Running {lib.upper()} library extractor...")

                lib_data = self._run_plugin_on_directory(plugin, root_dir, verbose)
                library_data[lib] = lib_data

                # Merge library-specific results
                if 'models' in lib_data:
                    results['models'].extend(lib_data['models'])
                if 'schemas' in lib_data:
                    results['schemas'].extend(lib_data['schemas'])
            else:
                if verbose:
                    print(f"   ⚠️  No plugin available for {lib}")

        # Store framework and library specific data
        results['framework_data'] = framework_data
        results['library_data'] = library_data

        if verbose:
            print(f"\n{'='*60}")
            print(f"✓ Universal scanning complete!")
            print(f"   Functions: {len(results['functions'])}")
            print(f"   Classes: {len(results['classes'])}")
            print(f"   Endpoints: {len(results['endpoints'])}")
            print(f"   Components: {len(results['components'])}")
            print(f"   Models: {len(results['models'])}")
            print(f"{'='*60}\n")

        return results

    def _run_plugin_on_directory(self, plugin: BasePlugin, root_dir: str, verbose: bool = True) -> Dict[str, Any]:
        """
        Run a single plugin on all relevant files in directory

        Args:
            plugin: Plugin to run
            root_dir: Project root
            verbose: Print progress

        Returns:
            Aggregated results from plugin
        """
        results = {}
        file_count = 0
        processed_count = 0

        # Walk directory
        for current_root, dirs, files in os.walk(root_dir):
            # Skip common directories
            dirs[:] = [d for d in dirs if d not in {
                '__pycache__', '.git', '.venv', 'venv', 'node_modules',
                'dist', 'build', 'target', '.next', '.nuxt'
            }]

            for file in files:
                if plugin.can_process(file):
                    file_count += 1
                    file_path = os.path.join(current_root, file)

                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                            content = f.read()

                        # Check if plugin should process this file
                        if plugin.detect(content, file_path):
                            processed_count += 1

                            if verbose and processed_count % 5 == 0:
                                print(f"   📄 Processing: {processed_count} files...", end='\r')

                            # Extract data
                            extracted = plugin.extract(content, file_path, root_dir)

                            # Merge results
                            for key, value in extracted.items():
                                if key not in results:
                                    results[key] = []
                                if isinstance(value, list):
                                    results[key].extend(value)
                                else:
                                    results[key].append(value)

                    except Exception as e:
                        if verbose:
                            rel_path = os.path.relpath(file_path, root_dir)
                            print(f"   WARNING: Failed to process {rel_path}: {e}")

        if verbose and processed_count > 0:
            print(f"   OK Processed {processed_count} files" + " " * 20)

        return results

    def get_available_plugins(self) -> Dict[str, List[str]]:
        """Get list of all registered plugins"""
        return {
            "languages": list(self.language_parsers.keys()),
            "frameworks": list(self.framework_plugins.keys()),
            "libraries": list(self.library_plugins.keys())
        }


# Global plugin manager instance
_plugin_manager = None


def get_plugin_manager() -> PluginManager:
    """Get global plugin manager instance"""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager
