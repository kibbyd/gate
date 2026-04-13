"""
Scanner package for Beast universal scanning capabilities.

This package provides:
- UniversalScanner: Directory scanning and file grouping
- LanguageDetector: File extension to language mapping
- FrameworkDetector: Pattern-based framework detection
"""

from .universal_scanner import UniversalScanner
from .language_detector import LanguageDetector
from .framework_detector import FrameworkDetector

__all__ = ['UniversalScanner', 'LanguageDetector', 'FrameworkDetector']
