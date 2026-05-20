from __future__ import annotations

"""
Framework-agnostic instrumentation session.

This is the core that manages instrumentation lifecycle, independent of any test framework.
Test framework adapters (pytest, Django, unittest, etc.) use this to instrument code.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable, Any, Protocol, runtime_checkable
import sys
import os

from .transformer import CodeTransformer
from .file_interceptor import FileInterceptor, ContentProvider
from .runtime_globals import RuntimeGlobals, CoverageData, TimeLog, ValueLog
from .source_map import SourceMap
from .events import (
    EventEmitter,
    EventType,
    FileLoadedEvent,
    FileInstrumentedEvent,
    InstrumentationEvent,
)


@runtime_checkable
class EventAdapter(Protocol):
    """
    Protocol for handling instrumentation events.
    
    Implementations handle events appropriately for their context
    (console output, JSON streaming, sending to external process, etc.).
    """
    
    def on_event(self, event: InstrumentationEvent) -> None:
        """Handle an instrumentation event."""
        ...
    
    def on_session_start(self) -> None:
        """Called when the instrumentation session starts."""
        ...
    
    def on_session_end(self) -> None:
        """Called when the instrumentation session ends."""
        ...


@dataclass
class InstrumentationConfig:
    """Configuration for instrumentation session."""
    
    project_root: str
    enable_coverage: bool = True
    enable_value_logging: bool = True
    rewrite_asserts: bool = False
    ignore_coverage: Optional[object] = None
    ignore_coverage_for_file: Optional[object] = None
    
    # Paths to instrument (relative to project_root or absolute)
    include_paths: list[str] = field(default_factory=lambda: ["src", "tests"])
    # Paths to exclude from instrumentation
    exclude_paths: list[str] = field(default_factory=lambda: [".venv", "venv", "node_modules"])
    
    def should_instrument(self, path: str) -> bool:
        """Check if a path should be instrumented."""
        resolved = str(Path(path).resolve())
        
        # Check excludes first
        for exclude in self.exclude_paths:
            if exclude in resolved:
                return False
        
        # Check if under project root
        if not resolved.startswith(str(Path(self.project_root).resolve())):
            return False
        
        return True


@dataclass
class InstrumentationSession:
    """
    Manages the lifecycle of code instrumentation.
    
    This is framework-agnostic - it doesn't know about pytest, Django, etc.
    Test framework adapters use this to:
    1. Start instrumentation before tests run
    2. Track per-test data during execution
    3. Stop instrumentation and collect results after tests complete
    
    Usage:
        from runner.adapters.base import ConsoleEventAdapter, DictContentProvider
        
        session = InstrumentationSession(
            config=InstrumentationConfig(project_root="/path/to/project"),
            event_adapter=ConsoleEventAdapter(),
            content_provider=my_content_provider,  # Optional
        )
        
        session.start()
        try:
            # Run tests with your framework of choice
            pytest.main([...])
        finally:
            session.stop()
        
        # Access results
        print(session.coverage)
    """
    
    config: InstrumentationConfig
    
    # Event adapter for handling lifecycle events (optional)
    event_adapter: Optional[EventAdapter] = None
    
    # Content provider for lazy file content loading (optional)
    content_provider: Optional[ContentProvider] = None

    # Log marker provider for logpoints (optional)
    log_marker_provider: Optional[Callable[[str], list[dict[str, Any]]]] = None
    
    # Event emitter for programmatic event subscription
    events: EventEmitter = field(default_factory=EventEmitter)
    
    # Components (created on start)
    transformer: Optional[CodeTransformer] = field(default=None, init=False)
    interceptor: Optional[FileInterceptor] = field(default=None, init=False)
    runtime: Optional[RuntimeGlobals] = field(default=None, init=False)
    
    # State
    _started: bool = field(default=False, init=False)
    _original_sys_path: list[str] = field(default_factory=list, init=False)
    
    # Legacy callbacks (deprecated - use events or event_adapter instead)
    on_coverage_hit: Optional[Callable[[str, int], None]] = None
    on_value_logged: Optional[Callable[[ValueLog], None]] = None
    on_print_called: Optional[Callable[[str, int, tuple, dict], None]] = None
    on_logpoint_called: Optional[Callable[[str, int, str, Any], None]] = None
    on_time_logged: Optional[Callable[[TimeLog], None]] = None
    on_file_transformed: Optional[Callable[[str, SourceMap], None]] = None
    on_used_logpoints: Optional[Callable[[str, list[str]], None]] = None
    on_transform_error: Optional[Callable[[str, Exception, str], None]] = None
    on_exec_error: Optional[Callable[[str, Exception], None]] = None
    
    def start(self) -> None:
        """Start instrumentation. Call before running tests."""
        if self._started:
            return
        
        # Connect event adapter to event emitter
        if self.event_adapter:
            self.events.on_event(self.event_adapter.on_event)
            self.event_adapter.on_session_start()
        
        # Create components
        self.transformer = CodeTransformer(
            enable_coverage=self.config.enable_coverage,
            enable_value_logging=self.config.enable_value_logging,
            rewrite_asserts=self.config.rewrite_asserts,
            ignore_coverage=self.config.ignore_coverage,
            ignore_coverage_for_file=self.config.ignore_coverage_for_file,
        )
        
        self.interceptor = FileInterceptor(transformer=self.transformer)
        self.interceptor.on_file_loaded = self._handle_file_loaded
        self.interceptor.on_file_transformed = self._handle_file_transformed
        self.interceptor.on_transform_error = self.on_transform_error
        self.interceptor.on_exec_error = self.on_exec_error
        self.interceptor.on_used_logpoints = self.on_used_logpoints
        self.interceptor.log_marker_provider = self.log_marker_provider
        
        # Connect content provider for lazy file loading
        if self.content_provider:
            self.interceptor.content_provider = self.content_provider
        
        self.runtime = RuntimeGlobals()
        self.runtime.on_coverage_hit = self.on_coverage_hit
        self.runtime.on_value_logged = self.on_value_logged
        self.runtime.on_print_called = self.on_print_called
        self.runtime.on_logpoint_called = self.on_logpoint_called
        self.runtime.on_time_logged = self.on_time_logged
        
        # Save original sys.path
        self._original_sys_path = sys.path.copy()
        
        # Add project root to path if not present
        if self.config.project_root not in sys.path:
            sys.path.insert(0, self.config.project_root)
        
        # Add src/ to sys.path for src-layout projects (where src/ is a
        # namespace directory without __init__.py, not a package itself)
        src_dir = os.path.join(self.config.project_root, 'src')
        if (os.path.isdir(src_dir)
                and not os.path.isfile(os.path.join(src_dir, '__init__.py'))
                and src_dir not in sys.path):
            sys.path.insert(1, src_dir)
        
        # Determine paths to intercept
        intercept_paths = []
        for include in self.config.include_paths:
            if os.path.isabs(include):
                intercept_paths.append(include)
            else:
                intercept_paths.append(os.path.join(self.config.project_root, include))
        
        # Also intercept project root
        intercept_paths.append(self.config.project_root)
        
        # Install hooks
        self.interceptor.install_import_hook(intercept_paths)
        self.runtime.install()
        
        self._started = True
    
    def stop(self) -> None:
        """Stop instrumentation. Call after tests complete."""
        if not self._started:
            return
        
        # Notify event adapter
        if self.event_adapter:
            self.event_adapter.on_session_end()
        
        # Uninstall hooks
        if self.runtime:
            self.runtime.uninstall()
        if self.interceptor:
            self.interceptor.uninstall_import_hook()
        
        # Restore sys.path
        sys.path = self._original_sys_path
        
        self._started = False
    
    def _handle_file_loaded(self, path: str) -> None:
        """Called when a file is loaded."""
        self.events.emit(FileLoadedEvent(path=path))
    
    def _handle_file_transformed(self, path: str, source_map: SourceMap) -> None:
        """Called when a file is transformed."""
        # Register total range count for this file
        if self.runtime and source_map.range_count > 0:
            self.runtime.coverage.total_ranges[path] = source_map.range_count
        
        # Emit instrumented event
        self.events.emit(FileInstrumentedEvent(
            path=path,
            original_lines=len(source_map.original_source.splitlines()) if source_map.original_source else 0,
            transformed_lines=source_map.transformed_line_count,
            covered_lines_count=len(source_map.covered_lines),
            range_count=source_map.range_count,
            ranges=source_map.ranges,
        ))
        
        # Notify external callback (legacy)
        if self.on_file_transformed:
            self.on_file_transformed(path, source_map)
    
    # --- Runtime globals ---
    
    def set_runtime_global(self, name: str, value: Any) -> None:
        """Set a global variable accessible to instrumented code."""
        if self.runtime:
            self.runtime.set_global(name, value)
    
    def get_runtime_global(self, name: str, default: Any = None) -> Any:
        """Get a runtime global variable."""
        if self.runtime:
            return self.runtime.get_global(name, default)
        return default
    
    # --- Source maps ---
    
    def get_source_map(self, path: str) -> Optional[SourceMap]:
        """Get source map for a file."""
        if self.interceptor:
            return self.interceptor.get_source_map(path)
        return None
    
    def translate_line(self, path: str, transformed_line: int) -> int:
        """Translate a transformed line number back to original."""
        source_map = self.get_source_map(path)
        if source_map:
            return source_map.translate_traceback_line(transformed_line)
        return transformed_line
    
    # --- Coverage data ---
    
    @property
    def coverage(self) -> Optional[CoverageData]:
        """Get coverage data."""
        if self.runtime:
            return self.runtime.coverage
        return None
    
    @property
    def value_logs(self) -> list[ValueLog]:
        """Get all logged values."""
        if self.runtime:
            return self.runtime.value_logs
        return []
    
    def get_coverage_snapshot(self) -> dict[str, set[int]]:
        """Get a snapshot of current coverage (for per-test tracking)."""
        if self.runtime:
            return {f: ranges.copy() for f, ranges in self.runtime.coverage.executed_ranges.items()}
        return {}
    
    def reset_per_test_tracking(self) -> None:
        """Reset per-test value logs (coverage accumulates)."""
        if self.runtime:
            self.runtime.value_logs.clear()
    
    # --- Context manager ---
    
    def __enter__(self) -> "InstrumentationSession":
        self.start()
        return self
    
    def __exit__(self, *args: Any) -> None:
        self.stop()
