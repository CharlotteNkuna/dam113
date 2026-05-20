"""
Adapters for different test frameworks and output formats.

This package contains:
- Event adapters for handling instrumentation events (console, quiet, composite)
- Content providers for lazy file loading (dict, callback, null)
- Framework integrations (pytest, etc.) - imported lazily to avoid requiring pytest
"""

from .base import (
    # Event Adapters
    ConsoleEventAdapter,
    QuietEventAdapter,
    CompositeEventAdapter,
    # Content Providers
    NullContentProvider,
    DictContentProvider,
    CallbackContentProvider,
)

# Note: pytest_plugin is NOT imported here to avoid requiring pytest at module load time.
# Import it directly where needed: from runner.adapters.pytest_plugin import InstrumentedTestPlugin

__all__ = [
    # Event Adapters
    "ConsoleEventAdapter",
    "QuietEventAdapter",
    "CompositeEventAdapter",
    # Content Providers
    "NullContentProvider",
    "DictContentProvider",
    "CallbackContentProvider",
]
