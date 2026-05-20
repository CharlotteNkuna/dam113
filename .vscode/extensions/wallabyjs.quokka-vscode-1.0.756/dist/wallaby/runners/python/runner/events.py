from __future__ import annotations

"""
Event system for instrumentation lifecycle.

Provides a unified event system that both the core session and framework
adapters can use to emit events during the instrumentation lifecycle.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional, Callable, Any, Union
from pathlib import Path


class EventType(Enum):
    """Types of events in the instrumentation lifecycle."""
    
    # File events
    FILE_LOADED = auto()           # A file was loaded
    FILE_INSTRUMENTED = auto()     # A file was transformed/instrumented
    
    # Collection events
    TESTS_COLLECTED = auto()       # All tests have been collected and are about to run
    
    # Test file events
    TEST_FILE_START = auto()       # Test file execution started
    TEST_FILE_END = auto()         # Test file execution ended
    
    # Individual test events
    TEST_START = auto()            # Individual test execution started
    TEST_END = auto()              # Individual test execution ended


class TestResult(Enum):
    """Result of a test execution."""
    
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    XFAILED = "xfailed"   # Expected failure
    XPASSED = "xpassed"   # Unexpected pass


@dataclass
class FileLoadedEvent:
    """Event emitted when a file is loaded."""
    
    event_type: EventType = field(default=EventType.FILE_LOADED, init=False)
    path: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        # Normalize path
        self.path = str(Path(self.path).resolve())


@dataclass
class FileInstrumentedEvent:
    """Event emitted when a file is instrumented."""
    
    event_type: EventType = field(default=EventType.FILE_INSTRUMENTED, init=False)
    path: str
    original_lines: int
    transformed_lines: int
    covered_lines_count: int  # Number of lines with coverage instrumentation
    range_count: int = 0  # Total number of coverage ranges
    ranges: list = field(default_factory=list)  # Range arrays: [startLine, startCol, endLine, endCol]
    timestamp: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        self.path = str(Path(self.path).resolve())


@dataclass
class TestInfo:
    """Information about a single test that will be run."""
    
    test_id: str          # Unique test identifier (e.g., nodeid in pytest)
    test_name: str        # Human-readable test name
    file_path: str
    line_number: int = 0  # Line number where test is defined
    
    def __post_init__(self):
        self.file_path = str(Path(self.file_path).resolve())


@dataclass
class TestsCollectedEvent:
    """Event emitted after test collection, before execution begins."""
    
    event_type: EventType = field(default=EventType.TESTS_COLLECTED, init=False)
    tests: list[TestInfo] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def test_count(self) -> int:
        """Total number of tests collected."""
        return len(self.tests)
    
    @property
    def files(self) -> list[str]:
        """Unique list of test files."""
        return list(dict.fromkeys(t.file_path for t in self.tests))
    
    @property
    def file_count(self) -> int:
        """Number of unique test files."""
        return len(self.files)
    
    def tests_in_file(self, file_path: str) -> list[TestInfo]:
        """Get all tests in a specific file."""
        normalized = str(Path(file_path).resolve())
        return [t for t in self.tests if t.file_path == normalized]


@dataclass
class TestFileStartEvent:
    """Event emitted when a test file starts execution."""
    
    event_type: EventType = field(default=EventType.TEST_FILE_START, init=False)
    path: str
    test_count: int = 0  # Number of tests in the file (if known)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        self.path = str(Path(self.path).resolve())


@dataclass
class TestFileEndEvent:
    """Event emitted when a test file finishes execution."""
    
    event_type: EventType = field(default=EventType.TEST_FILE_END, init=False)
    path: str
    passed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        self.path = str(Path(self.path).resolve())
    
    @property
    def total_count(self) -> int:
        return self.passed_count + self.failed_count + self.skipped_count + self.error_count


@dataclass
class TestStartEvent:
    """Event emitted when an individual test starts execution."""
    
    event_type: EventType = field(default=EventType.TEST_START, init=False)
    test_id: str          # Unique test identifier (e.g., nodeid in pytest)
    test_name: str        # Human-readable test name
    file_path: str
    line_number: int = 0  # Line number where test is defined
    timestamp: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        self.file_path = str(Path(self.file_path).resolve())


@dataclass 
class TestEndEvent:
    """Event emitted when an individual test finishes execution."""
    
    event_type: EventType = field(default=EventType.TEST_END, init=False)
    test_id: str
    test_name: str
    file_path: str
    result: TestResult
    duration_ms: float = 0.0
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None
    assertion_actual: Optional[str] = None
    assertion_expected: Optional[str] = None
    lines_covered: int = 0    # Lines covered by this specific test
    timestamp: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        self.file_path = str(Path(self.file_path).resolve())


# Union type for all events
InstrumentationEvent = Union[
    FileLoadedEvent,
    FileInstrumentedEvent,
    TestsCollectedEvent,
    TestFileStartEvent,
    TestFileEndEvent,
    TestStartEvent,
    TestEndEvent,
]

# Callback types
EventCallback = Callable[[InstrumentationEvent], None]
TypedEventCallback = Callable[[Any], None]  # For type-specific callbacks


class EventEmitter:
    """
    Event emitter for instrumentation events.
    
    Supports both general event handlers and type-specific handlers.
    
    Usage:
        emitter = EventEmitter()
        
        # General handler for all events
        emitter.on_event(lambda e: print(f"Event: {e.event_type}"))
        
        # Type-specific handler
        emitter.on(EventType.TEST_END, lambda e: print(f"Test ended: {e.result}"))
        
        # Emit events
        emitter.emit(TestEndEvent(...))
    """
    
    def __init__(self):
        self._handlers: list[EventCallback] = []
        self._typed_handlers: dict[EventType, list[TypedEventCallback]] = {}
    
    def on_event(self, callback: EventCallback) -> Callable[[], None]:
        """
        Register a handler for all events.
        Returns a function to unregister the handler.
        """
        self._handlers.append(callback)
        return lambda: self._handlers.remove(callback) if callback in self._handlers else None
    
    def on(self, event_type: EventType, callback: TypedEventCallback) -> Callable[[], None]:
        """
        Register a handler for a specific event type.
        Returns a function to unregister the handler.
        """
        if event_type not in self._typed_handlers:
            self._typed_handlers[event_type] = []
        self._typed_handlers[event_type].append(callback)
        return lambda: (
            self._typed_handlers[event_type].remove(callback)
            if event_type in self._typed_handlers and callback in self._typed_handlers[event_type]
            else None
        )
    
    def emit(self, event: InstrumentationEvent) -> None:
        """Emit an event to all registered handlers."""
        # Call general handlers
        for handler in self._handlers:
            try:
                handler(event)
            except Exception:
                # Don't let handler errors break the instrumentation
                pass
        
        # Call type-specific handlers
        event_type = event.event_type
        if event_type in self._typed_handlers:
            for handler in self._typed_handlers[event_type]:
                try:
                    handler(event)
                except Exception:
                    pass
    
    def clear(self) -> None:
        """Remove all event handlers."""
        self._handlers.clear()
        self._typed_handlers.clear()
