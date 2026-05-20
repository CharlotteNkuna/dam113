from __future__ import annotations

"""
Adapters for handling instrumentation events and providing content.

This module defines the interfaces that external integrations implement to:
1. Handle events (output to console, send to external process, etc.)
2. Provide file content on-demand (from cache, etc.)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Protocol, Callable
from datetime import datetime
from pathlib import Path

from ..events import (
    InstrumentationEvent,
    EventType,
    FileLoadedEvent,
    FileInstrumentedEvent,
    TestsCollectedEvent,
    TestFileStartEvent,
    TestFileEndEvent,
    TestStartEvent,
    TestEndEvent,
    TestResult,
)


class ContentProvider(Protocol):
    """
    Protocol for providing file content on-demand.
    
    Implementations can provide cached content, content from
    a virtual filesystem, or any other source. Content is fetched lazily
    when the file is actually needed (imported/executed).
    
    Example implementation:
        class CacheContentProvider:
            def __init__(self, file_metadata, cache_dir):
                self.file_metadata = file_metadata
                self.cache_dir = cache_dir
            
            def get_content(self, path: str) -> Optional[str]:
                file_info = self.file_metadata.get(path)
                if file_info:
                    cache_path = os.path.join(self.cache_dir, file_info['relative_path'])
                    with open(cache_path, 'r') as f:
                        return f.read()
                return None  # Use disk content
    """
    
    def get_content(self, path: str) -> Optional[str]:
        """
        Get content for a file path.
        
        Args:
            path: Absolute path to the file
            
        Returns:
            File content if available from this provider, None to use disk.
        """
        ...


class EventAdapter(ABC):
    """
    Abstract base class for event adapters.
    
    Event adapters receive instrumentation events and handle them
    appropriately for their context (console output, JSON streaming,
    sending to external process, etc.).
    """
    
    @abstractmethod
    def on_event(self, event: InstrumentationEvent) -> None:
        """Handle an instrumentation event."""
        ...
    
    def on_session_start(self) -> None:
        """Called when the instrumentation session starts."""
        pass
    
    def on_session_end(self) -> None:
        """Called when the instrumentation session ends."""
        pass


class ConsoleEventAdapter(EventAdapter):
    """
    Event adapter that outputs to the console.
    
    Provides formatted console output for all instrumentation events,
    suitable for CLI usage and development/debugging.
    """
    
    def __init__(
        self,
        verbose: bool = True,
        show_file_events: bool = True,
        show_test_timing: bool = True,
        use_color: bool = True,
        output: Callable[[str], None] = print,
    ):
        """
        Initialize console adapter.
        
        Args:
            verbose: Show detailed output (individual test events)
            show_file_events: Show file load/instrument events
            show_test_timing: Show timing information
            use_color: Use ANSI color codes (disable for non-TTY)
            output: Output function (default: print)
        """
        self.verbose = verbose
        self.show_file_events = show_file_events
        self.show_test_timing = show_test_timing
        self.use_color = use_color
        self.output = output
        
        # Statistics
        self._test_count = 0
        self._passed_count = 0
        self._failed_count = 0
        self._skipped_count = 0
        self._error_count = 0
        self._start_time: Optional[datetime] = None
    
    def _color(self, text: str, color: str) -> str:
        """Apply ANSI color if enabled."""
        if not self.use_color:
            return text
        
        colors = {
            "green": "\033[32m",
            "red": "\033[31m",
            "yellow": "\033[33m",
            "blue": "\033[34m",
            "cyan": "\033[36m",
            "gray": "\033[90m",
            "bold": "\033[1m",
            "reset": "\033[0m",
        }
        
        return f"{colors.get(color, '')}{text}{colors['reset']}"
    
    def _symbol(self, result: TestResult) -> str:
        """Get symbol for test result."""
        symbols = {
            TestResult.PASSED: self._color("✓", "green"),
            TestResult.FAILED: self._color("✗", "red"),
            TestResult.SKIPPED: self._color("○", "yellow"),
            TestResult.ERROR: self._color("!", "red"),
            TestResult.XFAILED: self._color("x", "yellow"),
            TestResult.XPASSED: self._color("X", "yellow"),
        }
        return symbols.get(result, "?")
    
    def on_session_start(self) -> None:
        """Called when the instrumentation session starts."""
        self._start_time = datetime.now()
        self._test_count = 0
        self._passed_count = 0
        self._failed_count = 0
        self._skipped_count = 0
        self._error_count = 0
        
        self.output(self._color("=" * 60, "bold"))
        self.output(self._color("INSTRUMENTATION SESSION STARTED", "bold"))
        self.output(self._color("=" * 60, "bold"))
    
    def on_session_end(self) -> None:
        """Called when the instrumentation session ends."""
        duration = (datetime.now() - self._start_time).total_seconds() if self._start_time else 0
        
        self.output("")
        self.output(self._color("-" * 60, "gray"))
        
        # Summary line
        passed_str = self._color(f"{self._passed_count} passed", "green") if self._passed_count else "0 passed"
        failed_str = self._color(f"{self._failed_count} failed", "red") if self._failed_count else ""
        skipped_str = self._color(f"{self._skipped_count} skipped", "yellow") if self._skipped_count else ""
        error_str = self._color(f"{self._error_count} errors", "red") if self._error_count else ""
        
        parts = [passed_str]
        if failed_str:
            parts.append(failed_str)
        if skipped_str:
            parts.append(skipped_str)
        if error_str:
            parts.append(error_str)
        
        summary = ", ".join(parts)
        self.output(f"Results: {summary} in {duration:.2f}s")
        self.output(self._color("=" * 60, "bold"))
    
    def on_event(self, event: InstrumentationEvent) -> None:
        """Handle an instrumentation event."""
        if isinstance(event, FileLoadedEvent):
            self._handle_file_loaded(event)
        elif isinstance(event, FileInstrumentedEvent):
            self._handle_file_instrumented(event)
        elif isinstance(event, TestsCollectedEvent):
            self._handle_tests_collected(event)
        elif isinstance(event, TestFileStartEvent):
            self._handle_test_file_start(event)
        elif isinstance(event, TestFileEndEvent):
            self._handle_test_file_end(event)
        elif isinstance(event, TestStartEvent):
            self._handle_test_start(event)
        elif isinstance(event, TestEndEvent):
            self._handle_test_end(event)
    
    def _handle_file_loaded(self, event: FileLoadedEvent) -> None:
        """Handle file loaded event."""
        if not self.show_file_events:
            return
        
        filename = Path(event.path).name
        self.output(f"  {self._color('📂', 'cyan')} Loaded: {filename}")
    
    def _handle_file_instrumented(self, event: FileInstrumentedEvent) -> None:
        """Handle file instrumented event."""
        if not self.show_file_events:
            return
        
        filename = Path(event.path).name
        details = f"{event.original_lines} → {event.transformed_lines} lines"
        if event.covered_lines_count:
            details += f", {event.covered_lines_count} coverage points"
        self.output(f"  {self._color('🔧', 'cyan')} Instrumented: {filename} ({details})")
    
    def _handle_tests_collected(self, event: TestsCollectedEvent) -> None:
        """Handle tests collected event."""
        self.output("")
        self.output(
            f"{self._color('📋', 'blue')} Collected "
            f"{self._color(str(event.test_count), 'bold')} tests "
            f"in {self._color(str(event.file_count), 'bold')} files"
        )
        
        if self.verbose:
            # Show tests grouped by file
            for file_path in event.files:
                filename = Path(file_path).name
                tests = event.tests_in_file(file_path)
                self.output(f"  {self._color('├─', 'gray')} {filename}: {len(tests)} tests")
                for test in tests:
                    line_info = f":{test.line_number}" if test.line_number else ""
                    self.output(f"  {self._color('│', 'gray')}   {test.test_name}{line_info}")
    
    def _handle_test_file_start(self, event: TestFileStartEvent) -> None:
        """Handle test file start event."""
        filename = Path(event.path).name
        self.output("")
        self.output(f"{self._color('📁', 'blue')} {self._color(filename, 'bold')}")
    
    def _handle_test_file_end(self, event: TestFileEndEvent) -> None:
        """Handle test file end event."""
        if not self.verbose:
            return
        
        filename = Path(event.path).name
        duration = f" [{event.duration_ms:.1f}ms]" if self.show_test_timing else ""
        summary = f"{event.passed_count} passed"
        if event.failed_count:
            summary += f", {event.failed_count} failed"
        if event.skipped_count:
            summary += f", {event.skipped_count} skipped"
        
        self.output(f"  {self._color('└─', 'gray')} {summary}{duration}")
    
    def _handle_test_start(self, event: TestStartEvent) -> None:
        """Handle test start event."""
        # In verbose mode, we'll show the test name when it ends with result
        # In non-verbose mode, we show a dot progress indicator
        if not self.verbose:
            # Print dot for progress (no newline)
            self.output(".", end="")
    
    def _handle_test_end(self, event: TestEndEvent) -> None:
        """Handle test end event."""
        self._test_count += 1
        
        # Update counters
        if event.result == TestResult.PASSED:
            self._passed_count += 1
        elif event.result == TestResult.FAILED:
            self._failed_count += 1
        elif event.result == TestResult.SKIPPED:
            self._skipped_count += 1
        elif event.result == TestResult.ERROR:
            self._error_count += 1
        
        if self.verbose:
            symbol = self._symbol(event.result)
            timing = f" ({event.duration_ms:.2f}ms)" if self.show_test_timing else ""
            coverage = f" [{event.lines_covered} lines]" if event.lines_covered else ""
            
            self.output(f"  {symbol} {event.test_name}{timing}{coverage}")
            
            # Show error details for failures
            if event.error_message and event.result in (TestResult.FAILED, TestResult.ERROR):
                self.output(f"    {self._color(event.error_message, 'red')}")


class QuietEventAdapter(EventAdapter):
    """
    Minimal event adapter that only shows summary.
    
    Useful for CI environments or when only the final result matters.
    """
    
    def __init__(self, output: Callable[[str], None] = print):
        self.output = output
        self._passed = 0
        self._failed = 0
        self._errors = 0
        self._start_time: Optional[datetime] = None
    
    def on_session_start(self) -> None:
        self._start_time = datetime.now()
        self._passed = 0
        self._failed = 0
        self._errors = 0
    
    def on_session_end(self) -> None:
        duration = (datetime.now() - self._start_time).total_seconds() if self._start_time else 0
        total = self._passed + self._failed + self._errors
        
        if self._failed or self._errors:
            self.output(f"FAILED: {self._passed}/{total} passed in {duration:.2f}s")
        else:
            self.output(f"OK: {self._passed} passed in {duration:.2f}s")
    
    def on_event(self, event: InstrumentationEvent) -> None:
        if isinstance(event, TestEndEvent):
            if event.result == TestResult.PASSED:
                self._passed += 1
            elif event.result == TestResult.FAILED:
                self._failed += 1
            elif event.result == TestResult.ERROR:
                self._errors += 1


class CompositeEventAdapter(EventAdapter):
    """
    Adapter that forwards events to multiple adapters.
    
    Useful for logging to console AND sending to external process.
    """
    
    def __init__(self, adapters: list[EventAdapter]):
        self.adapters = adapters
    
    def on_session_start(self) -> None:
        for adapter in self.adapters:
            adapter.on_session_start()
    
    def on_session_end(self) -> None:
        for adapter in self.adapters:
            adapter.on_session_end()
    
    def on_event(self, event: InstrumentationEvent) -> None:
        for adapter in self.adapters:
            adapter.on_event(event)


@dataclass
class NullContentProvider:
    """Content provider that always returns None (use disk content)."""
    
    def get_content(self, path: str) -> Optional[str]:
        return None


@dataclass
class DictContentProvider:
    """
    Content provider backed by a dictionary.
    
    Simple implementation for testing or when all content is known upfront.
    """
    
    content: dict[str, str] = field(default_factory=dict)
    
    def get_content(self, path: str) -> Optional[str]:
        # Normalize path
        normalized = str(Path(path).resolve())
        return self.content.get(normalized)
    
    def set_content(self, path: str, content: str) -> None:
        """Set content for a path."""
        normalized = str(Path(path).resolve())
        self.content[normalized] = content
    
    def remove_content(self, path: str) -> None:
        """Remove content for a path."""
        normalized = str(Path(path).resolve())
        self.content.pop(normalized, None)
    
    def clear(self) -> None:
        """Clear all content."""
        self.content.clear()


class CallbackContentProvider:
    """
    Content provider that delegates to a callback function.
    
    Useful for integrating with external systems that have their own
    way of providing content.
    """
    
    def __init__(self, callback: Callable[[str], Optional[str]]):
        """
        Initialize with a callback.
        
        Args:
            callback: Function that takes a path and returns content or None
        """
        self.callback = callback
    
    def get_content(self, path: str) -> Optional[str]:
        return self.callback(path)
