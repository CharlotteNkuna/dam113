from __future__ import annotations

"""Runtime globals for instrumented code."""

import builtins
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from collections import defaultdict


def _noop_coverage_callback(_file: str, _range_id: int) -> None:
    return None


def _passthrough_value_callback(
    _file: str,
    _line: int,
    _name: str,
    value: Any,
    range_id: Optional[int] = None,
    change_id: Optional[Any] = None,
    trace_id: Optional[Any] = None,
    exp: Optional[Any] = None,
    context: Optional[str] = None,
    auto_expand: bool = False,
) -> Any:
    return value


def _noop_time_callback() -> float:
    import time

    return time.perf_counter() * 1000


def _passthrough_timed_log_callback(
    _file: str,
    _range_id: int,
    _context: str,
    _start: float,
    value: Any,
    _end: float,
) -> Any:
    return value


def _fallback_print_callback(_file: str, _range_id: int, *args: Any, **kwargs: Any) -> Any:
    print(*args, **kwargs)
    return args[0] if args else None


def _passthrough_logpoint_callback(_file: str, _range_id: int, _logpoint_id: str, value: Any) -> Any:
    return value



@dataclass
class CoverageData:
    """Tracks code coverage data."""
    
    # file -> set of executed range IDs
    executed_ranges: dict[str, set[int]] = field(default_factory=lambda: defaultdict(set))
    # file -> total number of ranges
    total_ranges: dict[str, int] = field(default_factory=dict)
    
    def record_hit(self, file: str, range_id: int) -> None:
        """Record that a range was executed."""
        self.executed_ranges[file].add(range_id)
    
    def get_coverage_percent(self, file: Optional[str] = None) -> float:
        """Get coverage percentage for a file or all files."""
        if file:
            total = self.total_ranges.get(file, 0)
            executed = len(self.executed_ranges.get(file, set()))
        else:
            total = sum(self.total_ranges.values())
            executed = sum(len(ranges) for ranges in self.executed_ranges.values())
        
        return (executed / total * 100) if total > 0 else 0.0
    
    def get_uncovered_ranges(self, file: str) -> set[int]:
        """Get set of ranges not yet executed."""
        total = self.total_ranges.get(file, 0)
        all_ranges = set(range(total))
        return all_ranges - self.executed_ranges.get(file, set())
    
    def reset(self) -> None:
        """Reset all coverage data."""
        self.executed_ranges.clear()
        self.total_ranges.clear()


@dataclass
class ValueLog:
    """A logged runtime value."""
    
    file: str
    line: int
    name: str
    value: Any
    timestamp: float = 0.0
    range_id: Optional[int] = None
    change_id: Optional[Any] = None
    trace_id: Optional[Any] = None
    exp: Optional[Any] = None
    context: Optional[str] = None
    auto_expand: bool = False


@dataclass
class TimeLog:
    """A logged timing measurement."""

    file: str
    range_id: int
    context: str
    elapsed_ms: float


@dataclass
class RuntimeGlobals:
    """
    Manages global runtime variables for instrumented code.
    These are injected into builtins so instrumented code can access them.
    """
    
    coverage: CoverageData = field(default_factory=CoverageData)
    value_logs: list[ValueLog] = field(default_factory=list)
    custom_globals: dict[str, Any] = field(default_factory=dict)
    
    # Callbacks for real-time notifications
    on_coverage_hit: Optional[Callable[[str, int], None]] = None
    on_value_logged: Optional[Callable[[ValueLog], None]] = None
    on_print_called: Optional[Callable[[str, int, tuple, dict], None]] = None
    on_logpoint_called: Optional[Callable[[str, int, str, Any], None]] = None
    on_time_logged: Optional[Callable[[TimeLog], None]] = None
    
    _installed: bool = False
    _original_builtins: dict[str, Any] = field(default_factory=dict)
    
    def install(self) -> None:
        """Install runtime globals into builtins."""
        if self._installed:
            return
        
        # Save originals if they exist
        for name in [
            "__runner_coverage__",
            "__runner_log_value__",
            "__runner_print__",
            "__runner_logpoint__",
            "__runner_log_time__",
            "__runner_time__",
            "__runner_globals__",
        ]:
            if hasattr(builtins, name):
                self._original_builtins[name] = getattr(builtins, name)
        
        # Install our functions
        builtins.__runner_coverage__ = self._coverage_callback  # type: ignore
        builtins.__runner_log_value__ = self._value_callback  # type: ignore
        builtins.__runner_print__ = self._print_callback  # type: ignore
        builtins.__runner_logpoint__ = self._logpoint_callback  # type: ignore
        builtins.__runner_log_time__ = self._timed_log_callback  # type: ignore
        builtins.__runner_time__ = self._time_callback  # type: ignore
        builtins.__runner_globals__ = self.custom_globals  # type: ignore
        
        self._installed = True
    
    def uninstall(self) -> None:
        """Remove runtime globals from builtins."""
        if not self._installed:
            return
        
        for name in [
            "__runner_coverage__",
            "__runner_log_value__",
            "__runner_print__",
            "__runner_logpoint__",
            "__runner_log_time__",
            "__runner_time__",
            "__runner_globals__",
        ]:
            if name in self._original_builtins:
                setattr(builtins, name, self._original_builtins[name])
            elif name == "__runner_coverage__":
                setattr(builtins, name, _noop_coverage_callback)
            elif name == "__runner_log_value__":
                setattr(builtins, name, _passthrough_value_callback)
            elif name == "__runner_print__":
                setattr(builtins, name, _fallback_print_callback)
            elif name == "__runner_logpoint__":
                setattr(builtins, name, _passthrough_logpoint_callback)
            elif name == "__runner_log_time__":
                setattr(builtins, name, _passthrough_timed_log_callback)
            elif name == "__runner_time__":
                setattr(builtins, name, _noop_time_callback)
            elif name == "__runner_globals__":
                setattr(builtins, name, {})
        
        self._original_builtins.clear()
        self._installed = False
    
    def _coverage_callback(self, file: str, range_id: int) -> None:
        """Called by instrumented code when a range is executed."""
        self.coverage.record_hit(file, range_id)
        if self.on_coverage_hit:
            self.on_coverage_hit(file, range_id)
        # Debug: If no callback, this coverage hit is not being sent to tracer
        # else:
        #     print(f"WARNING: on_coverage_hit not set for {file}:{range_id}")
    
    def _value_callback(
        self,
        file: str,
        line: int,
        name: str,
        value: Any,
        range_id: Optional[int] = None,
        change_id: Optional[Any] = None,
        trace_id: Optional[Any] = None,
        exp: Optional[Any] = None,
        context: Optional[str] = None,
        auto_expand: bool = False,
    ) -> Any:
        """Called by instrumented code to log a value. Returns the value for chaining."""
        import time
        
        log = ValueLog(
            file=file,
            line=line,
            name=name,
            value=value,
            timestamp=time.time(),
            range_id=range_id,
            change_id=change_id,
            trace_id=trace_id,
            exp=exp,
            context=context,
            auto_expand=auto_expand,
        )
        self.value_logs.append(log)
        
        if self.on_value_logged:
            self.on_value_logged(log)
        
        return value
    
    def _print_callback(self, file: str, range_id: int, *args: Any, **kwargs: Any) -> Any:
        """
        Called by instrumented code when print() is called or a magic comment is used.
        
        Returns the first positional arg (if any) so that return statements with
        magic comments can preserve semantics: return __runner_print__(file, id, expr)
        
        Args:
            file: Source file path
            range_id: Range ID for the print statement location
            *args: Arguments passed to print()
            **kwargs: Keyword arguments passed to print()
        """
        # Extract auto_expand before passing kwargs to print handler
        auto_expand = kwargs.pop('auto_expand', None)
        if self.on_print_called:
            self.on_print_called(file, range_id, args, kwargs, auto_expand=auto_expand)
        else:
            # Fallback to regular print if no handler is set
            print(*args, **kwargs)
        return args[0] if args else None

    def _logpoint_callback(self, file: str, range_id: int, logpoint_id: str, value: Any) -> Any:
        """
        Called by instrumented code when a logpoint is hit.

        Returns the value so expressions preserve semantics.
        """
        if self.on_logpoint_called:
            self.on_logpoint_called(file, range_id, logpoint_id, value)
        return value

    def _time_callback(self) -> float:
        import time

        return time.perf_counter() * 1000

    def _timed_log_callback(
        self,
        file: str,
        range_id: int,
        context: str,
        start: float,
        value: Any,
        end: float,
    ) -> Any:
        elapsed_ms = max(float(end) - float(start), 0.0)
        if self.on_time_logged:
            self.on_time_logged(
                TimeLog(
                    file=file,
                    range_id=range_id,
                    context=context,
                    elapsed_ms=elapsed_ms,
                )
            )
        return value
    
    def set_global(self, name: str, value: Any) -> None:
        """Set a custom global variable accessible to instrumented code."""
        self.custom_globals[name] = value
    
    def get_global(self, name: str, default: Any = None) -> Any:
        """Get a custom global variable."""
        return self.custom_globals.get(name, default)
    
    def clear_global(self, name: str) -> None:
        """Remove a custom global variable."""
        self.custom_globals.pop(name, None)
    
    def get_value_logs_for_line(self, file: str, line: int) -> list[ValueLog]:
        """Get all logged values for a specific file and line."""
        return [log for log in self.value_logs if log.file == file and log.line == line]
    
    def get_value_logs_for_file(self, file: str) -> list[ValueLog]:
        """Get all logged values for a file."""
        return [log for log in self.value_logs if log.file == file]
    
    def reset(self) -> None:
        """Reset all runtime data."""
        self.coverage.reset()
        self.value_logs.clear()
        # Keep custom globals - they're typically configuration
    
    def __enter__(self) -> "RuntimeGlobals":
        """Context manager entry."""
        self.install()
        return self
    
    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.uninstall()
