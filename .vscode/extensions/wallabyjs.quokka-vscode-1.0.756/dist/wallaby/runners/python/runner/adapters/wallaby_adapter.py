from __future__ import annotations

"""
Wallaby Event Adapter - Translates runner events to Wallaby tracer calls.

This adapter bridges the python-experiments runner events with the Wallaby
tracer protocol, enabling test results, coverage, and value logging to be
communicated to the Wallaby parent process.
"""

from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from pathlib import Path
import time

from ..runtime_globals import TimeLog, ValueLog


# Comparison operators ordered by specificity (longer/more specific patterns first).
# Each entry: (operator string with surrounding spaces, formatter function).
_COMPARISON_OPERATORS: List[Tuple[str, Callable[[str, str], str]]] = [
    (' is not ', lambda l, r: f'Expected {l} not to be {r}'),
    (' not in ', lambda l, r: f'Expected {l} not to be in {r}'),
    (' is ', lambda l, r: f'Expected {l} to be {r}'),
    (' in ', lambda l, r: f'Expected {l} to be in {r}'),
    (' >= ', lambda l, r: f'Expected {l} to be >= {r}'),
    (' <= ', lambda l, r: f'Expected {l} to be <= {r}'),
    (' != ', lambda l, r: f'Expected {l} to not equal {r}'),
    (' == ', lambda l, r: f'Expected: {r}\nReceived: {l}'),
    (' > ', lambda l, r: f'Expected {l} to be > {r}'),
    (' < ', lambda l, r: f'Expected {l} to be < {r}'),
]


def _transform_assertion_message(msg: str) -> str:
    """Transform pytest assertion rewriting output to user-friendly format.

    Handles common comparison patterns (==, !=, <, >, in, is, etc.)
    and falls back to 'Assertion failed: <expr>' for unrecognized patterns.
    Preserves 'where' clauses as additional context.
    """
    if not msg:
        return msg

    lines = msg.split('\n')
    first_line = lines[0]

    # Only transform messages that start with 'assert ' (pytest rewriting format)
    if not first_line.startswith('assert '):
        return msg

    expr = first_line[7:]  # Strip 'assert ' prefix
    rest_lines = lines[1:]

    # Try each known operator, splitting conservatively (exactly 2 parts required)
    for op_str, formatter in _COMPARISON_OPERATORS:
        parts = expr.split(op_str)
        if len(parts) == 2:
            transformed = formatter(parts[0].strip(), parts[1].strip())
            if rest_lines:
                return transformed + '\n' + '\n'.join(rest_lines)
            return transformed

    # Boolean or unrecognized assertion pattern
    if rest_lines:
        return f'Assertion failed: {expr}\n' + '\n'.join(rest_lines)
    return f'Assertion failed: {expr}'


from ..events import (
    InstrumentationEvent,
    EventType,
    TestsCollectedEvent,
    TestFileStartEvent,
    TestFileEndEvent,
    TestStartEvent,
    TestEndEvent,
    TestResult,
    FileInstrumentedEvent,
)


class WallabyEventAdapter:
    """
    Event adapter that translates runner events to Wallaby tracer calls.
    
    This adapter:
    - Maps file paths to Wallaby file IDs
    - Calls tracer lifecycle methods (spec_start, spec_end, result, etc.)
    - Tracks per-test coverage data
    - Manages test ID sequencing
    """
    
    def __init__(
        self,
        tracer: Any,
        file_path_to_id: Dict[str, int],
        test_file_ids: Set[int],
        project_root: str,
        log: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize the Wallaby event adapter.
        
        Args:
            tracer: The Wallaby tracer instance
            file_path_to_id: Mapping from absolute file paths to Wallaby file IDs
            test_file_ids: Set of file IDs that are test files
            project_root: Project root directory
            log: Optional logging function (e.g., from TestWorker)
        """
        self._tracer = tracer
        self._file_path_to_id = file_path_to_id
        self._test_file_ids = test_file_ids
        self._project_root = Path(project_root).resolve()
        self._log = log or (lambda msg: None)  # No-op if no log function provided
        
        # Test tracking
        self._next_spec_id = 1
        self._test_id_to_spec_id: Dict[str, int] = {}
        self._test_id_to_line_number: Dict[str, int] = {}
        self._current_spec_id: Optional[int] = None
        self._current_test_path: List[str] = []
        self._current_test_start_time: float = 0.0
        self._spec_sync_started: Set[int] = set()
        
        # Parent test tracking (for nested tests/describe blocks)
        self._parent_tests: List[int] = []
        
        # Coverage tracking per test
        self._pre_test_coverage: Dict[int, Set[int]] = {}

        # Map runtime range ids (instrumentation order) to source-order ids per file
        self._range_id_maps: Dict[int, Dict[int, int]] = {}
        # Store sorted ranges and line-to-range maps for test declaration mapping
        self._sorted_ranges: Dict[int, List[List[int]]] = {}
        self._line_to_range: Dict[int, Dict[int, int]] = {}

        # Track logpoints reported as used
        self._used_logpoints_by_path: Dict[str, Set[str]] = {}
    
    def _get_file_id(self, path: str) -> Optional[int]:
        """Get Wallaby file ID for a path."""
        normalized = str(Path(path).resolve())
        return self._file_path_to_id.get(normalized)
    
    def _normalize_path(self, path: str) -> str:
        """Get path relative to project root."""
        try:
            return str(Path(path).resolve().relative_to(self._project_root))
        except ValueError:
            return path
    
    def on_session_start(self) -> None:
        """Called when instrumentation session starts."""
        self._log('WallabyAdapter: session start')
        # Log all file path mappings for debugging
        self._log(f'WallabyAdapter: file_path_to_id mappings ({len(self._file_path_to_id)} files):')
        for path, file_id in self._file_path_to_id.items():
            self._log(f'  {path} -> {file_id}')
    
    def on_session_end(self) -> None:
        """Called when instrumentation session ends."""
        self._log('WallabyAdapter: session end')
    
    def on_event(self, event: InstrumentationEvent) -> None:
        """Handle an instrumentation event."""
        event_type = event.event_type
        
        if event_type == EventType.FILE_LOADED:
            self._on_file_loaded(event)
        elif event_type == EventType.TESTS_COLLECTED:
            self._on_tests_collected(event)
        elif event_type == EventType.TEST_FILE_START:
            self._on_test_file_start(event)
        elif event_type == EventType.TEST_FILE_END:
            self._on_test_file_end(event)
        elif event_type == EventType.TEST_START:
            self._on_test_start(event)
        elif event_type == EventType.TEST_END:
            self._on_test_end(event)
        elif event_type == EventType.FILE_INSTRUMENTED:
            self._on_file_instrumented(event)

    def _on_file_loaded(self, event: Any) -> None:
        """Record non-test module imports during the loading phase."""
        file_id = self._get_file_id(event.path)
        self._log(f'WallabyAdapter: file loaded, path={event.path}, file_id={file_id}')
        if file_id is None or file_id in self._test_file_ids:
            return

        self._tracer.program_scope_start_loading(file_id)
        self._tracer.program_scope_end_loading(file_id)
    
    def _on_tests_collected(self, event: TestsCollectedEvent) -> None:
        """Handle tests collected event - assign spec IDs."""
        self._log(f'WallabyAdapter: tests collected, count={len(event.tests)}')
        for test_info in event.tests:
            spec_id = self._next_spec_id
            self._next_spec_id += 1
            self._test_id_to_spec_id[test_info.test_id] = spec_id
            self._log(f'  assigned spec_id={spec_id} to test_id={test_info.test_id}')
    
    def _on_test_file_start(self, event: TestFileStartEvent) -> None:
        """Handle test file start event."""
        file_id = self._get_file_id(event.path)
        self._log(f'WallabyAdapter: test file start, path={event.path}, file_id={file_id}')
        if file_id is not None:
            # Set entry file for tracer
            self._tracer._spec_file_id = file_id
            
            # Notify tracer about program scope start
            self._tracer.program_scope_start_loading(file_id)
    
    def _on_test_file_end(self, event: TestFileEndEvent) -> None:
        """Handle test file end event."""
        file_id = self._get_file_id(event.path)
        self._log(f'WallabyAdapter: test file end, path={event.path}, file_id={file_id}')
        if file_id is not None:
            self._tracer.program_scope_end_loading(file_id)
    
    def _on_file_instrumented(self, event: FileInstrumentedEvent) -> None:
        """Handle file instrumented event - initialize coverage tracking and notify core."""
        file_id = self._get_file_id(event.path)
        self._log(f'WallabyAdapter: file instrumented, path={event.path}, file_id={file_id}, range_count={event.range_count}')
        self._log(f'  ranges: {event.ranges}')
        if file_id is not None:
            ranges = event.ranges or []
            if ranges:
                sorted_entries = sorted(
                    enumerate(ranges),
                    key=lambda item: (item[1][0], item[1][1], item[1][2], item[1][3], item[0]),
                )
                event.ranges = [entry[1] for entry in sorted_entries]
                self._range_id_maps[file_id] = {
                    old_index: new_index for new_index, (old_index, _) in enumerate(sorted_entries)
                }
            else:
                self._range_id_maps[file_id] = {}
            self._sorted_ranges[file_id] = event.ranges
            line_map: Dict[int, int] = {}
            for idx, rng in enumerate(event.ranges):
                if not rng or len(rng) < 2:
                    continue
                line = rng[0]
                if line not in line_map:
                    line_map[line] = idx
            self._line_to_range[file_id] = line_map

            # Initialize coverage array for this file using range_count
            self._tracer.initialize_coverage(file_id, event.range_count)
            self._log(f'  initialized coverage for file_id={file_id}')
            
            # Send transformed file info to core (for coverage indicators)
            # Must match RunnerTransformedFile type from lib/types/all.ts:
            # - id: file ID
            # - transformed: { map?: string } - required, use empty object since Python has no source maps
            # - instrumented: { ranges, ... } - ranges from instrumentation
            # - transformedTime: timestamp (ISO string is fine, matches Vitest)
            # - lineMap: optional line mapping
            self._tracer.send_transformed_file({
                'id': file_id,
                'transformed': {},  # No source map transforms for Python
                'instrumented': {
                    'ranges': event.ranges
                },
                'transformedTime': event.timestamp.isoformat()
            })
            self._log(f'  sent transformedFile message with {len(event.ranges)} ranges')
    
    def _on_test_start(self, event: TestStartEvent) -> None:
        """Handle test start event - call tracer.spec_start."""
        spec_id = self._test_id_to_spec_id.get(event.test_id)
        if spec_id is None:
            # Assign spec ID on-the-fly if not pre-collected
            spec_id = self._next_spec_id
            self._next_spec_id += 1
            self._test_id_to_spec_id[event.test_id] = spec_id
            self._log(f'WallabyAdapter: test start (on-the-fly), test_id={event.test_id}, spec_id={spec_id}')
        else:
            self._log(f'WallabyAdapter: test start, test_id={event.test_id}, spec_id={spec_id}')
        
        file_id = self._get_file_id(event.file_path)
        
        # Build test path from nodeid (e.g., "test_file.py::TestClass::test_method")
        test_path = self._build_test_path(event.test_id, event.test_name)
        
        self._current_spec_id = spec_id
        self._current_test_path = test_path
        self._current_test_start_time = time.time() * 1000  # ms
        if event.line_number:
            self._test_id_to_line_number[event.test_id] = event.line_number
        
        # Store parent test relationship
        self._parent_tests.append(spec_id)
        
        # Call tracer spec_start
        self._tracer.spec_start(
            spec_id=spec_id,
            name=event.test_name,
            spec_file_id=file_id or 0,
            path=test_path,
        )
        self._log(f'  called spec_start: name={event.test_name}, file_id={file_id}, path={test_path}')

        if file_id is not None and event.line_number:
            start_range_id = self._find_test_start_range(file_id, event.line_number)
            if start_range_id is not None:
                self._tracer.set_spec_start_range(file_id, start_range_id)
                self._log(f'  preset spec start range: line={event.line_number}, range_id={start_range_id}')

    def on_test_call_start(self, test_id: str) -> None:
        """Mark the beginning of the pytest call phase for a test."""
        spec_id = self._test_id_to_spec_id.get(test_id)
        if spec_id is None:
            self._log(f'WallabyAdapter: test call start, test_id={test_id} - NO SPEC ID FOUND')
            return

        if spec_id in self._spec_sync_started:
            return

        self._tracer.spec_sync_start()
        self._spec_sync_started.add(spec_id)
        self._log(f'WallabyAdapter: test call start, test_id={test_id}, spec_id={spec_id}')
    
    def _on_test_end(self, event: TestEndEvent) -> None:
        """Handle test end event - call tracer.spec_end and result."""
        spec_id = self._test_id_to_spec_id.get(event.test_id)
        if spec_id is None:
            self._log(f'WallabyAdapter: test end, test_id={event.test_id} - NO SPEC ID FOUND')
            return
        
        self._log(f'WallabyAdapter: test end, test_id={event.test_id}, spec_id={spec_id}, result={event.result}')
        
        file_id = self._get_file_id(event.file_path)
        
        # End sync execution range only if call phase started.
        if spec_id in self._spec_sync_started:
            self._tracer.spec_sync_end()
            self._spec_sync_started.discard(spec_id)
        
        # Call spec_end to get the test range
        test_range = self._tracer.spec_end()
        self._log(f'  spec_end returned test_range={test_range}')
        
        # Pop from parent tests
        if self._parent_tests and self._parent_tests[-1] == spec_id:
            self._parent_tests.pop()
        
        # Calculate duration
        duration = event.duration_ms
        
        # Build suite path (test path without the last element)
        test_path = self._build_test_path(event.test_id, event.test_name)
        suite_path = test_path[:-1] if test_path else []
        
        # Determine status - skipped/todo are special, everything else is 'executed'
        if event.result == TestResult.SKIPPED:
            status = 'skipped'
        elif event.result == TestResult.XFAILED:
            status = 'skipped'  # Expected failure treated as skip
        else:
            status = 'executed'  # Pass and fail both use 'executed', failures go in log
        
        # Send result to tracer
        result_data = {
            'id': spec_id,
            'testRange': test_range,
            'name': event.test_name,
            'suite': suite_path,
            'status': status,
            'time': int(duration),
            'log': [],
            'testFile': file_id,
            'parentTests': list(self._parent_tests),
        }

        declaration_line = self._test_id_to_line_number.get(event.test_id)
        if declaration_line:
            result_data['declaration'] = [declaration_line, 0, declaration_line, 0]
        
        self._log(f'  event.result={event.result}, error_message={event.error_message}')
        
        # Add error to log array with passed: false (same pattern as Vitest)
        if event.result in (TestResult.FAILED, TestResult.ERROR):
            error_msg = _transform_assertion_message(event.error_message) if event.error_message else 'Test failed'
            error_stack = event.error_traceback or event.error_message or 'Test failed'
            failed_expectation = {}
            if event.assertion_actual is not None and event.assertion_expected is not None:
                failed_expectation = {
                    'showDiff': True,
                    'actual': event.assertion_actual,
                    'expected': event.assertion_expected,
                }
            error_entry = self._tracer.set_assertion_data(
                failed_expectation,
                {
                    'message': error_msg,
                    'stack': error_stack,
                    'passed': False,
                }
            )
            result_data['log'].append(error_entry)
            self._log(f'  added error to log: message={error_msg[:100]}')
        
        # Remove empty log array
        if not result_data['log']:
            del result_data['log']
        
        self._tracer.result(result_data)
        self._log(f'  sent result: status={status}, duration={int(duration)}ms, testFile={file_id}')

        self._current_spec_id = None
        self._test_id_to_line_number.pop(event.test_id, None)
        self._current_test_path = []
    
    def _build_test_path(self, test_id: str, test_name: str) -> List[str]:
        """
        Build test path from pytest nodeid.
        
        Examples:
            "tests/test_calc.py::test_add" -> ["test_add"]
            "tests/test_calc.py::TestCalc::test_add" -> ["TestCalc", "test_add"]
        """
        # Split on :: to get components
        parts = test_id.split("::")
        
        # Skip the file path part (first element)
        if len(parts) > 1:
            return parts[1:]
        
        return [test_name]

    def _find_test_start_range(self, file_id: int, line_number: int) -> Optional[int]:
        """
        Find a range id to use as the test start for a given line.

        Prefers the first statement inside the test function body (so the
        declaration range can be inferred), falling back to the declaration
        range itself.
        """
        ranges = self._sorted_ranges.get(file_id)
        if not ranges or not line_number:
            return None

        decl_index = self._line_to_range.get(file_id, {}).get(line_number)
        if decl_index is None:
            for idx, rng in enumerate(ranges):
                if rng and len(rng) >= 2 and rng[0] == line_number:
                    decl_index = idx
                    break
        if decl_index is None:
            return None

        decl_range = ranges[decl_index] if decl_index < len(ranges) else None
        if not decl_range or len(decl_range) < 4:
            return decl_index

        decl_start_line, decl_start_col, decl_end_line, _ = decl_range

        for idx in range(decl_index + 1, len(ranges)):
            rng = ranges[idx]
            if not rng or len(rng) < 4:
                continue
            start_line, start_col, end_line, _ = rng
            if start_line > decl_end_line:
                break
            if start_line < decl_start_line:
                continue
            if start_line == decl_start_line and start_col <= decl_start_col:
                continue
            if end_line > decl_end_line:
                continue
            return idx

        return decl_index
    
    def record_coverage_hit(self, file_path: str, range_id: int) -> None:
        """
        Record a coverage hit for the current test.
        
        Called by the runtime globals when a range is executed.
        Translates file path to file ID and calls tracer.statement().
        
        Args:
            file_path: The absolute path of the file
            range_id: The range ID within the file
        """
        file_id = self._get_file_id(file_path)
        if file_id is not None:
            mapped_range_id = self._range_id_maps.get(file_id, {}).get(range_id, range_id)
            self._tracer.statement(file_id, mapped_range_id)
        else:
            # Debug: log when we can't find a file ID
            self._log(f'WallabyAdapter: record_coverage_hit - no file_id for path={file_path}, range_id={range_id}')    
    def record_print_call(
        self, 
        file_path: str, 
        range_id: int, 
        args: tuple, 
        kwargs: dict,
        auto_expand: bool = None,
    ) -> None:
        """
        Handle print() calls from instrumented code.
        
        This translates file path to file ID and calls the tracer's
        print_with_location method to create expandable object trees
        in the value viewer.
        
        Args:
            file_path: The absolute path of the file containing the print call
            range_id: The range ID for the print statement location
            args: Arguments passed to print()
            kwargs: Keyword arguments passed to print()
            auto_expand: If explicitly set, override the default auto-expand behavior
        """
        self._log(f'WallabyAdapter: record_print_call called: file_path={file_path}, range_id={range_id}, args={args}')
        file_id = self._get_file_id(file_path)
        self._log(f'WallabyAdapter: record_print_call file_id={file_id}')
        if file_id is not None:
            self._log(f'WallabyAdapter: calling tracer.print_with_location')
            mapped_range_id = self._range_id_maps.get(file_id, {}).get(range_id, range_id)
            self._tracer.print_with_location(file_id, mapped_range_id, args, kwargs, auto_expand=auto_expand)
            self._log(f'WallabyAdapter: tracer.print_with_location returned')
        else:
            # Fallback: Use tracer's internal _log method which captures console output
            # This preserves the original print capture behavior when file ID not found
            self._log(f'WallabyAdapter: record_print_call - no file_id for path={file_path}')
            self._tracer._do_when_receiver_ready(
                lambda: self._tracer._log(*args)
            )

    def record_logpoint_call(
        self,
        file_path: str,
        range_id: int,
        logpoint_id: str,
        value: Any,
    ) -> None:
        """Handle logpoint calls from instrumented code."""
        file_id = self._get_file_id(file_path)
        if file_id is not None:
            mapped_range_id = self._range_id_maps.get(file_id, {}).get(range_id, range_id)
            self._tracer.logpoint(file_id, mapped_range_id, logpoint_id, value)
            self._mark_used_logpoint(file_path, logpoint_id)

    def record_value_log(self, log: ValueLog) -> None:
        """Handle auto-log value markers from instrumented code."""
        file_id = self._get_file_id(log.file)
        if file_id is None:
            return
        if log.range_id is None:
            return
        mapped_range_id = self._range_id_maps.get(file_id, {}).get(log.range_id, log.range_id)
        context = log.context or log.name or None
        self._tracer.auto_log(
            file_id=file_id,
            range_id=mapped_range_id,
            value=log.value,
            change_id=log.change_id,
            trace_id=log.trace_id,
            exp=log.exp,
            context=context,
            auto_expand=log.auto_expand,
        )

    def record_time_log(self, log: TimeLog) -> None:
        """Handle timed live-comment measurements from instrumented code."""
        file_id = self._get_file_id(log.file)
        if file_id is None:
            return
        mapped_range_id = self._range_id_maps.get(file_id, {}).get(log.range_id, log.range_id)
        self._tracer.auto_time(
            file_id=file_id,
            range_id=mapped_range_id,
            elapsed_ms=log.elapsed_ms,
            context=log.context,
        )

    def report_used_logpoints(self, path: str, logpoints: list[str]) -> None:
        """Report logpoints that were instrumented in a file."""
        if not logpoints:
            return
        rel_path = self._normalize_path(path)
        self._tracer.logpoints_used(rel_path, logpoints)

    def _mark_used_logpoint(self, path: str, logpoint_id: str) -> None:
        rel_path = self._normalize_path(path)
        used = self._used_logpoints_by_path.setdefault(rel_path, set())
        if logpoint_id in used:
            return
        used.add(logpoint_id)
        self._tracer.logpoints_used(rel_path, [logpoint_id])
