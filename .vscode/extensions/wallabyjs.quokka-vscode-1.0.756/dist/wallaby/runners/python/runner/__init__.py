"""Custom test runner with code instrumentation, file interception, and source mapping."""

from .source_map import SourceMap, LineMapping
from .transformer import CodeTransformer
from .file_interceptor import FileInterceptor
from .runtime_globals import RuntimeGlobals
from .test_runner import TestRunner
from .session import InstrumentationSession, InstrumentationConfig, ContentProvider, EventAdapter
from .events import (
    EventEmitter,
    EventType,
    TestResult,
    TestInfo,
    FileLoadedEvent,
    FileInstrumentedEvent,
    TestsCollectedEvent,
    TestFileStartEvent,
    TestFileEndEvent,
    TestStartEvent,
    TestEndEvent,
    InstrumentationEvent,
)
from .adapters.base import (
    ConsoleEventAdapter,
    QuietEventAdapter,
    CompositeEventAdapter,
    NullContentProvider,
    DictContentProvider,
    CallbackContentProvider,
)

__all__ = [
    # Core components
    "SourceMap",
    "LineMapping", 
    "CodeTransformer",
    "FileInterceptor",
    "RuntimeGlobals",
    # Framework-agnostic session
    "InstrumentationSession",
    "InstrumentationConfig",
    # Protocols/Interfaces
    "ContentProvider",
    "EventAdapter",
    # Event Adapters
    "ConsoleEventAdapter",
    "QuietEventAdapter",
    "CompositeEventAdapter",
    # Content Providers
    "NullContentProvider",
    "DictContentProvider",
    "CallbackContentProvider",
    # Events
    "EventEmitter",
    "EventType",
    "TestResult",
    "TestInfo",
    "FileLoadedEvent",
    "FileInstrumentedEvent",
    "TestsCollectedEvent",
    "TestFileStartEvent",
    "TestFileEndEvent",
    "TestStartEvent",
    "TestEndEvent",
    "InstrumentationEvent",
    # Standalone runner (for simple cases)
    "TestRunner",
]
