"""
Base plugin interface for Beast parsers
All framework and library detectors inherit from these base classes
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class PluginMetadata:
    """Metadata for a plugin"""
    name: str                      # e.g., "react", "express", "sequelize"
    category: str                  # "framework" or "library"
    language: str                  # "python", "javascript", "typescript", "java"
    file_extensions: List[str]     # [".jsx", ".tsx", ".js", ".ts"]
    package_indicators: List[str]  # ["react", "react-dom"] - for package.json/requirements.txt


class BasePlugin(ABC):
    """Base class for all parser plugins"""

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata"""
        pass

    @abstractmethod
    def detect(self, file_content: str, file_path: str) -> bool:
        """
        Returns True if this file uses this framework/library

        Args:
            file_content: Full content of the file
            file_path: Absolute path to the file

        Returns:
            True if plugin should process this file
        """
        pass

    @abstractmethod
    def extract(self, file_content: str, file_path: str, root_dir: str) -> Dict[str, Any]:
        """
        Extract framework/library-specific data from file

        Args:
            file_content: Full content of the file
            file_path: Absolute path to the file
            root_dir: Project root directory (for relative paths)

        Returns:
            Dictionary with extracted data (structure varies by plugin)
            Example for React:
            {
                "components": [...],
                "hooks": [...],
                "contexts": [...]
            }
        """
        pass

    def can_process(self, file_path: str) -> bool:
        """
        Check if this plugin can process this file based on extension

        Args:
            file_path: File path to check

        Returns:
            True if file extension matches plugin's supported extensions
        """
        return any(file_path.endswith(ext) for ext in self.metadata.file_extensions)


class FrameworkPlugin(BasePlugin):
    """
    Base class for framework detectors (React, Express, Flask, etc.)
    Frameworks define the core architecture
    """
    pass


class LibraryPlugin(BasePlugin):
    """
    Base class for library extractors (Material-UI, Sequelize, Mongoose, etc.)
    Libraries add specific functionality on top of frameworks
    """
    pass


class LanguageParser(ABC):
    """
    Base class for language-level parsers (Python, JavaScript, Java)
    These provide the AST/parsing foundation
    """

    @property
    @abstractmethod
    def language(self) -> str:
        """Return language name"""
        pass

    @property
    @abstractmethod
    def file_extensions(self) -> List[str]:
        """Return supported file extensions"""
        pass

    @abstractmethod
    def parse_file(self, file_path: str, root_dir: str) -> Dict[str, Any]:
        """
        Parse a single file and extract basic code structure

        Args:
            file_path: Absolute path to file
            root_dir: Project root directory

        Returns:
            {
                "functions": [...],
                "classes": [...],
                "imports": [...],
                "exports": [...]
            }
        """
        pass

    @abstractmethod
    def parse_directory(self, root_dir: str, verbose: bool = True) -> Dict[str, Any]:
        """
        Parse entire directory recursively

        Args:
            root_dir: Directory to parse
            verbose: Print progress messages

        Returns:
            Aggregated results from all files
        """
        pass
