"""
Language detection based on file extensions.

Maps file extensions to programming languages.
"""

import os
from typing import Dict, List, Set


class LanguageDetector:
    """Detects programming languages based on file extensions."""

    # Map file extensions to language names
    LANGUAGE_MAP = {
        ('.js', '.jsx'): 'javascript',
        ('.ts', '.tsx'): 'typescript',
        ('.py', '.pyw'): 'python',
        ('.java',): 'java',
        ('.go',): 'go',
        ('.rs',): 'rust',
        ('.rb',): 'ruby',
        ('.php',): 'php',
        ('.cs',): 'csharp',
        ('.cpp', '.cc', '.cxx', '.hpp', '.hxx'): 'cpp',
        ('.c', '.h'): 'c',
        ('.kt', '.kts'): 'kotlin',
        ('.swift',): 'swift',
        ('.m', '.mm'): 'objective-c',
        ('.dart',): 'dart',
        ('.scala',): 'scala',
        ('.clj', '.cljs'): 'clojure',
        ('.ex', '.exs'): 'elixir',
        ('.erl', '.hrl'): 'erlang',
        ('.lua',): 'lua',
        ('.r', '.R'): 'r',
        ('.sh', '.bash'): 'shell',
        ('.ps1',): 'powershell',
        ('.sql',): 'sql',
        ('.vue',): 'vue',
        ('.svelte',): 'svelte',
    }

    def __init__(self):
        """Initialize the language detector."""
        # Create reverse mapping: extension -> language
        self.ext_to_lang = {}
        for extensions, language in self.LANGUAGE_MAP.items():
            for ext in extensions:
                self.ext_to_lang[ext] = language

    def detect_language(self, file_path: str) -> str:
        """
        Detect the programming language of a file based on its extension.

        Args:
            file_path: Path to the file

        Returns:
            Language name (e.g., 'python', 'javascript') or 'unknown'
        """
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        return self.ext_to_lang.get(ext, 'unknown')

    def group_files_by_language(self, file_paths: List[str]) -> Dict[str, List[str]]:
        """
        Group a list of file paths by their detected language.

        Args:
            file_paths: List of file paths

        Returns:
            Dictionary mapping language name to list of files
            Example: {'python': ['main.py', 'utils.py'], 'javascript': ['app.js']}
        """
        grouped = {}
        for file_path in file_paths:
            language = self.detect_language(file_path)
            if language != 'unknown':
                if language not in grouped:
                    grouped[language] = []
                grouped[language].append(file_path)
        return grouped

    def get_detected_languages(self, file_paths: List[str]) -> Set[str]:
        """
        Get a set of all detected languages from a list of files.

        Args:
            file_paths: List of file paths

        Returns:
            Set of language names (excluding 'unknown')
        """
        languages = set()
        for file_path in file_paths:
            language = self.detect_language(file_path)
            if language != 'unknown':
                languages.add(language)
        return languages

    def get_supported_languages(self) -> List[str]:
        """
        Get list of all supported languages.

        Returns:
            Sorted list of language names
        """
        return sorted(set(self.LANGUAGE_MAP.values()))

    def get_extensions_for_language(self, language: str) -> List[str]:
        """
        Get all file extensions associated with a language.

        Args:
            language: Language name (e.g., 'python')

        Returns:
            List of extensions (e.g., ['.py', '.pyw'])
        """
        extensions = []
        for exts, lang in self.LANGUAGE_MAP.items():
            if lang == language:
                extensions.extend(exts)
        return extensions
