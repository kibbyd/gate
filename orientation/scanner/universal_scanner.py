"""
Universal directory scanner for Beast.

Scans directories, groups files by language, and detects frameworks automatically.
"""

import os
from typing import Dict, List, Set
from .language_detector import LanguageDetector
from .framework_detector import FrameworkDetector


class UniversalScanner:
    """
    Universal scanner that analyzes a codebase and detects:
    - All programming languages used
    - All frameworks and libraries used
    - File structure and organization
    """

    # Directories to skip during scanning
    SKIP_DIRS = {
        '__pycache__',
        '.git',
        '.venv',
        'venv',
        'node_modules',
        'dist',
        'build',
        'target',
        'out',
        '.idea',
        '.vscode',
        '.next',
        '.nuxt',
        'coverage',
        '.pytest_cache',
        '.mypy_cache',
        'vendor',
        'bower_components',
    }

    # Binary and non-source file extensions to skip
    SKIP_EXTENSIONS = {
        '.pyc', '.pyo', '.so', '.dll', '.dylib',
        '.exe', '.bin', '.obj', '.o',
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.svg',
        '.mp3', '.mp4', '.wav', '.avi', '.mov',
        '.pdf', '.doc', '.docx', '.xls', '.xlsx',
        '.zip', '.tar', '.gz', '.rar', '.7z',
        '.lock', '.log',
    }

    def __init__(self, verbose: bool = True):
        """
        Initialize the universal scanner.

        Args:
            verbose: Whether to print scanning progress
        """
        self.verbose = verbose
        self.language_detector = LanguageDetector()
        self.framework_detector = FrameworkDetector(verbose=verbose)

    def scan_directory(self, root_dir: str) -> Dict:
        """
        Scan a directory and detect everything.

        Args:
            root_dir: Root directory to scan

        Returns:
            Dictionary containing:
            {
                'root_dir': str,
                'all_files': List[str],  # All source files (relative paths)
                'files_by_language': Dict[str, List[str]],  # Language -> file list
                'detected_languages': List[str],  # Sorted list of languages
                'detected_frameworks': List[str],  # Detected frameworks
                'detected_libraries': List[str],  # Detected libraries
                'file_count': int,  # Total source files
                'dir_count': int,  # Total directories scanned
            }
        """
        if self.verbose:
            print(f"\n[Universal Scanner] Scanning directory: {root_dir}")

        # Step 1: Walk directory and collect all source files
        all_files = []
        dir_count = 0

        for dirpath, dirnames, filenames in os.walk(root_dir):
            # Filter out directories to skip (modify in-place)
            dirnames[:] = [d for d in dirnames if d not in self.SKIP_DIRS]
            dir_count += 1

            # Get relative path from root
            rel_dir = os.path.relpath(dirpath, root_dir)

            for filename in filenames:
                # Skip files with binary/non-source extensions
                _, ext = os.path.splitext(filename)
                if ext.lower() in self.SKIP_EXTENSIONS:
                    continue

                # Get relative file path
                if rel_dir == '.':
                    rel_path = filename
                else:
                    rel_path = os.path.join(rel_dir, filename)

                all_files.append(rel_path)

        if self.verbose:
            print(f"  Found {len(all_files)} source files in {dir_count} directories")

        # Step 2: Group files by language
        if self.verbose:
            print(f"\n[Language Detection] Analyzing file extensions...")

        files_by_language = self.language_detector.group_files_by_language(all_files)
        detected_languages = sorted(files_by_language.keys())

        if self.verbose:
            print(f"  Detected languages: {', '.join(detected_languages) if detected_languages else 'none'}")
            for lang, files in files_by_language.items():
                print(f"    - {lang}: {len(files)} files")

        # Step 3: Detect frameworks and libraries
        if self.verbose:
            print(f"\n[Framework Detection] Analyzing project structure...")

        detection_results = self.framework_detector.detect_frameworks(
            root_dir,
            sample_files=all_files
        )

        detected_frameworks = detection_results['frameworks']
        detected_libraries = detection_results['libraries']

        if self.verbose:
            if detected_frameworks:
                print(f"  Detected frameworks: {', '.join(detected_frameworks)}")
            else:
                print(f"  No frameworks detected")

            if detected_libraries:
                print(f"  Detected libraries: {', '.join(detected_libraries)}")

        # Step 4: Return results
        return {
            'root_dir': root_dir,
            'all_files': all_files,
            'files_by_language': files_by_language,
            'detected_languages': detected_languages,
            'detected_frameworks': detected_frameworks,
            'detected_libraries': detected_libraries,
            'file_count': len(all_files),
            'dir_count': dir_count,
        }

    def quick_scan(self, root_dir: str) -> Dict:
        """
        Quick scan that only checks dependency files (no content scanning).

        Much faster than full scan, but may miss some frameworks.

        Args:
            root_dir: Root directory to scan

        Returns:
            Same structure as scan_directory() but with potentially fewer detections
        """
        if self.verbose:
            print(f"\n[Universal Scanner - Quick Mode] Scanning: {root_dir}")

        # Collect files
        all_files = []
        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if d not in self.SKIP_DIRS]
            rel_dir = os.path.relpath(dirpath, root_dir)

            for filename in filenames:
                _, ext = os.path.splitext(filename)
                if ext.lower() not in self.SKIP_EXTENSIONS:
                    rel_path = filename if rel_dir == '.' else os.path.join(rel_dir, filename)
                    all_files.append(rel_path)

        # Group by language
        files_by_language = self.language_detector.group_files_by_language(all_files)
        detected_languages = sorted(files_by_language.keys())

        # Only check dependency files (no content scanning)
        detection_results = self.framework_detector.detect_frameworks(
            root_dir,
            sample_files=None  # Skip content scanning
        )

        return {
            'root_dir': root_dir,
            'all_files': all_files,
            'files_by_language': files_by_language,
            'detected_languages': detected_languages,
            'detected_frameworks': detection_results['frameworks'],
            'detected_libraries': detection_results['libraries'],
            'file_count': len(all_files),
            'dir_count': 0,
        }

    def get_stats(self, scan_results: Dict) -> str:
        """
        Get a formatted summary of scan results.

        Args:
            scan_results: Results from scan_directory()

        Returns:
            Formatted string summary
        """
        lines = []
        lines.append(f"\n{'='*60}")
        lines.append(f"Scan Results for: {scan_results['root_dir']}")
        lines.append(f"{'='*60}")
        lines.append(f"Files: {scan_results['file_count']}")
        lines.append(f"Directories: {scan_results['dir_count']}")
        lines.append(f"\nLanguages ({len(scan_results['detected_languages'])}):")
        for lang in scan_results['detected_languages']:
            count = len(scan_results['files_by_language'][lang])
            lines.append(f"  - {lang}: {count} files")

        if scan_results['detected_frameworks']:
            lines.append(f"\nFrameworks ({len(scan_results['detected_frameworks'])}):")
            for fw in scan_results['detected_frameworks']:
                lines.append(f"  - {fw}")

        if scan_results['detected_libraries']:
            lines.append(f"\nLibraries ({len(scan_results['detected_libraries'])}):")
            for lib in scan_results['detected_libraries']:
                lines.append(f"  - {lib}")

        lines.append(f"{'='*60}\n")
        return '\n'.join(lines)
