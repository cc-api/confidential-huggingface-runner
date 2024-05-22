"""
Package to provide confidential AI loader
"""

__version__ = "0.1.0"

from .loader import HuggingFaceLoader

hf_cli = HuggingFaceLoader.hf_cli
