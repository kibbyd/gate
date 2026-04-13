"""
Framework detection based on patterns, imports, and dependencies.

Detects web frameworks and libraries by analyzing:
- Dependency files (package.json, requirements.txt, pom.xml, etc.)
- Import statements in code files
- Framework-specific patterns (decorators, file structures)
"""

import os
import json
import re
from typing import Dict, List, Set


class FrameworkDetector:
    """Detects frameworks and libraries used in a project."""

    # Framework detection patterns
    FRAMEWORK_PATTERNS = {
        'react': {
            'dependency_files': ['package.json'],
            'dependency_keys': ['react', 'react-dom'],
            'content_patterns': [
                r'import\s+.*\s+from\s+["\']react["\']',
                r'useState|useEffect|useContext|useReducer',
                r'React\.FC|React\.Component',
                r'<[A-Z]\w+.*>',  # JSX components
            ],
            'file_patterns': [r'\.jsx$', r'\.tsx$']
        },
        'express': {
            'dependency_files': ['package.json'],
            'dependency_keys': ['express'],
            'content_patterns': [
                r'require\(["\']express["\']\)',
                r'from\s+["\']express["\']',
                r'app\.(get|post|put|delete|patch)\(',
                r'router\.(get|post|put|delete|patch)\(',
                r'express\(\)',
            ],
            'file_patterns': []
        },
        'nextjs': {
            'dependency_files': ['package.json'],
            'dependency_keys': ['next'],
            'content_patterns': [
                r'from\s+["\']next/',
                r'import.*from.*["\']next/',
                r'export\s+default\s+function',
                r'getServerSideProps|getStaticProps',
            ],
            'file_patterns': [r'next\.config\.js$', r'pages/.*\.(js|ts)x?$']
        },
        'vue': {
            'dependency_files': ['package.json'],
            'dependency_keys': ['vue'],
            'content_patterns': [
                r'import.*from\s+["\']vue["\']',
                r'<template>',
                r'<script.*setup.*>',
            ],
            'file_patterns': [r'\.vue$']
        },
        'angular': {
            'dependency_files': ['package.json'],
            'dependency_keys': ['@angular/core'],
            'content_patterns': [
                r'import.*from\s+["\']@angular/',
                r'@Component\(',
                r'@NgModule\(',
            ],
            'file_patterns': []
        },
        'fastapi': {
            'dependency_files': ['requirements.txt', 'pyproject.toml', 'setup.py'],
            'dependency_keys': ['fastapi'],
            'content_patterns': [
                r'from\s+fastapi\s+import',
                r'@app\.(get|post|put|delete|patch)',
                r'FastAPI\(',
                r'APIRouter\(',
            ],
            'file_patterns': []
        },
        'django': {
            'dependency_files': ['requirements.txt', 'pyproject.toml', 'setup.py'],
            'dependency_keys': ['django'],
            'content_patterns': [
                r'from\s+django',
                r'import\s+django',
                r'INSTALLED_APPS',
                r'urlpatterns',
            ],
            'file_patterns': [r'manage\.py$', r'settings\.py$', r'urls\.py$']
        },
        'flask': {
            'dependency_files': ['requirements.txt', 'pyproject.toml', 'setup.py'],
            'dependency_keys': ['flask'],
            'content_patterns': [
                r'from\s+flask\s+import',
                r'Flask\(',
                r'@app\.route\(',
            ],
            'file_patterns': []
        },
        'spring': {
            'dependency_files': ['pom.xml', 'build.gradle'],
            'dependency_keys': ['spring-boot', 'springframework'],
            'content_patterns': [
                r'@SpringBootApplication',
                r'@RestController',
                r'@Controller',
                r'@GetMapping|@PostMapping|@PutMapping|@DeleteMapping',
                r'import\s+org\.springframework',
            ],
            'file_patterns': []
        },
        'gin': {
            'dependency_files': ['go.mod'],
            'dependency_keys': ['github.com/gin-gonic/gin'],
            'content_patterns': [
                r'import.*"github\.com/gin-gonic/gin"',
                r'gin\.Engine',
                r'\.GET\(|\.POST\(|\.PUT\(|\.DELETE\(',
            ],
            'file_patterns': []
        },
        'chefscript': {
            'dependency_files': [],
            'dependency_keys': [],
            'content_patterns': [
                r'engine\.RegisterPage\(',
                r'engine\.RegisterAction\(',
                r'engine\.Register\w*Components?\(',
            ],
            'file_patterns': [r'pages/.*\.json$', r'engine/components.*\.go$']
        },
    }

    # Library detection patterns (for common libraries)
    LIBRARY_PATTERNS = {
        'mongoose': {
            'dependency_files': ['package.json'],
            'dependency_keys': ['mongoose'],
            'content_patterns': [r'require\(["\']mongoose["\']\)', r'mongoose\.'],
        },
        'sequelize': {
            'dependency_files': ['package.json'],
            'dependency_keys': ['sequelize'],
            'content_patterns': [r'require\(["\']sequelize["\']\)', r'Sequelize'],
        },
        'material-ui': {
            'dependency_files': ['package.json'],
            'dependency_keys': ['@mui/material', '@material-ui/core'],
            'content_patterns': [r'from\s+["\']@mui/', r'from\s+["\']@material-ui/'],
        },
        'tailwind': {
            'dependency_files': ['package.json'],
            'dependency_keys': ['tailwindcss'],
            'content_patterns': [],
        },
        'postgresql': {
            'dependency_files': ['package.json', 'requirements.txt'],
            'dependency_keys': ['pg', 'psycopg2', 'asyncpg'],
            'content_patterns': [],
        },
        'mongodb': {
            'dependency_files': ['package.json', 'requirements.txt'],
            'dependency_keys': ['mongodb', 'pymongo'],
            'content_patterns': [],
        },
    }

    def __init__(self, verbose: bool = True):
        """
        Initialize the framework detector.

        Args:
            verbose: Whether to print detection progress
        """
        self.verbose = verbose

    def detect_frameworks(self, root_dir: str, sample_files: List[str] = None) -> Dict[str, List[str]]:
        """
        Detect frameworks and libraries used in a project.

        Args:
            root_dir: Root directory of the project
            sample_files: Optional list of sample files to scan for patterns

        Returns:
            Dictionary with 'frameworks' and 'libraries' keys, each containing a list of detected items
            Example: {'frameworks': ['react', 'express'], 'libraries': ['mongoose']}
        """
        detected_frameworks = set()
        detected_libraries = set()

        # Step 1: Check dependency files (fast and accurate)
        dep_frameworks, dep_libraries = self._check_dependency_files(root_dir)
        detected_frameworks.update(dep_frameworks)
        detected_libraries.update(dep_libraries)

        # Step 2: Check file patterns (file names and structures)
        if sample_files:
            pattern_frameworks = self._check_file_patterns(sample_files)
            detected_frameworks.update(pattern_frameworks)

            # Step 3: Check content patterns (sample files only, for speed)
            content_frameworks, content_libraries = self._check_content_patterns(
                root_dir, sample_files[:20]  # Only check first 20 files
            )
            detected_frameworks.update(content_frameworks)
            detected_libraries.update(content_libraries)

        return {
            'frameworks': sorted(list(detected_frameworks)),
            'libraries': sorted(list(detected_libraries))
        }

    def _check_dependency_files(self, root_dir: str) -> tuple:
        """Check dependency files for framework/library declarations."""
        frameworks = set()
        libraries = set()

        # Check package.json (Node.js)
        package_json = os.path.join(root_dir, 'package.json')
        if os.path.exists(package_json):
            try:
                with open(package_json, 'r', encoding='utf-8', errors='replace') as f:
                    data = json.load(f)
                    dependencies = {
                        **data.get('dependencies', {}),
                        **data.get('devDependencies', {})
                    }

                    # Check frameworks
                    for framework, config in self.FRAMEWORK_PATTERNS.items():
                        if 'package.json' in config['dependency_files']:
                            if any(key in dependencies for key in config['dependency_keys']):
                                frameworks.add(framework)
                                if self.verbose:
                                    print(f"  [Dependency] Detected framework: {framework}")

                    # Check libraries
                    for library, config in self.LIBRARY_PATTERNS.items():
                        if 'package.json' in config['dependency_files']:
                            if any(key in dependencies for key in config['dependency_keys']):
                                libraries.add(library)
                                if self.verbose:
                                    print(f"  [Dependency] Detected library: {library}")
            except (json.JSONDecodeError, IOError):
                pass

        # Check requirements.txt (Python)
        requirements_txt = os.path.join(root_dir, 'requirements.txt')
        if os.path.exists(requirements_txt):
            try:
                with open(requirements_txt, 'r', encoding='utf-8', errors='replace') as f:
                    requirements = f.read().lower()

                    # Check frameworks
                    for framework, config in self.FRAMEWORK_PATTERNS.items():
                        if 'requirements.txt' in config['dependency_files']:
                            if any(key.lower() in requirements for key in config['dependency_keys']):
                                frameworks.add(framework)
                                if self.verbose:
                                    print(f"  [Dependency] Detected framework: {framework}")

                    # Check libraries
                    for library, config in self.LIBRARY_PATTERNS.items():
                        if 'requirements.txt' in config['dependency_files']:
                            if any(key.lower() in requirements for key in config['dependency_keys']):
                                libraries.add(library)
                                if self.verbose:
                                    print(f"  [Dependency] Detected library: {library}")
            except IOError:
                pass

        # Check go.mod (Go)
        go_mod = os.path.join(root_dir, 'go.mod')
        if os.path.exists(go_mod):
            try:
                with open(go_mod, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()

                    for framework, config in self.FRAMEWORK_PATTERNS.items():
                        if 'go.mod' in config['dependency_files']:
                            if any(key in content for key in config['dependency_keys']):
                                frameworks.add(framework)
                                if self.verbose:
                                    print(f"  [Dependency] Detected framework: {framework}")
            except IOError:
                pass

        return frameworks, libraries

    def _check_file_patterns(self, file_paths: List[str]) -> Set[str]:
        """Check file names and paths for framework-specific patterns."""
        frameworks = set()

        for file_path in file_paths:
            file_name = os.path.basename(file_path)
            rel_path = file_path.replace('\\', '/')  # Normalize path separators

            for framework, config in self.FRAMEWORK_PATTERNS.items():
                for pattern in config['file_patterns']:
                    if re.search(pattern, file_name) or re.search(pattern, rel_path):
                        frameworks.add(framework)
                        if self.verbose:
                            print(f"  [File Pattern] Detected framework: {framework} (file: {file_name})")
                        break

        return frameworks

    def _check_content_patterns(self, root_dir: str, file_paths: List[str]) -> tuple:
        """Check file contents for framework-specific patterns."""
        frameworks = set()
        libraries = set()

        for file_path in file_paths:
            try:
                full_path = os.path.join(root_dir, file_path) if not os.path.isabs(file_path) else file_path
                with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()

                    # Check frameworks
                    for framework, config in self.FRAMEWORK_PATTERNS.items():
                        for pattern in config['content_patterns']:
                            if re.search(pattern, content):
                                frameworks.add(framework)
                                if self.verbose:
                                    print(f"  [Content Pattern] Detected framework: {framework} (file: {os.path.basename(file_path)})")
                                break

                    # Check libraries
                    for library, config in self.LIBRARY_PATTERNS.items():
                        for pattern in config['content_patterns']:
                            if pattern and re.search(pattern, content):
                                libraries.add(library)
                                if self.verbose:
                                    print(f"  [Content Pattern] Detected library: {library} (file: {os.path.basename(file_path)})")
                                break

            except (IOError, UnicodeDecodeError):
                continue

        return frameworks, libraries

    def get_supported_frameworks(self) -> List[str]:
        """Get list of all supported frameworks."""
        return sorted(self.FRAMEWORK_PATTERNS.keys())

    def get_supported_libraries(self) -> List[str]:
        """Get list of all supported libraries."""
        return sorted(self.LIBRARY_PATTERNS.keys())
