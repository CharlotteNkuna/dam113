#!/usr/bin/env python3
"""
Python Tracer - Runtime Value Capture and Test Execution Tracking

This module provides runtime instrumentation for Python test execution,
capturing values, coverage data, and test results. It maintains the same
message contract as the JavaScript tracer for communication with the
parent Wallaby process.
"""

import sys
import json
import time
import traceback
import inspect
import pprint
import copy
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps

# Attempt to import typing extensions for better type hints
try:
    from typing import TypedDict
except ImportError:
    TypedDict = dict


# Debug logging for print callback chain
_DEBUG_LOG_FILE = '/Users/smcenlly/repos/temp/python-experiments/examples/calculator/log.txt'

def _debug_log(message: str) -> None:
    """Write debug message to log file."""
    try:
        with open(_DEBUG_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f'[{datetime.now().isoformat()}] [tracer] {message}\n')
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Configuration Constants
# -----------------------------------------------------------------------------

MAX_LOG_ENTRY_SIZE = 16384
MAX_TRACE_STEPS = 999999
MAX_TRACE_STEPS_FOR_WATCH_EXPRESSION_PREFETCH = 10
EVALUATED_EXPRESSION_PER_RANGE_LIMIT = 10000
IDENTIFIER_EXPRESSION_AUTO_LOG_HIT_LIMIT = 10
IDENTIFIER_PROPERTY_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

# Sentinel for JS-like undefined handling in tests/parity scenarios
UNDEFINED = object()

# Default log limits
DEFAULT_LOG_LIMITS = {
    'inline': {
        'depth': 5,
        'elements': 5000,
    },
    'values': {
        'default': {
            'stringLength': 8192,
        },
        'autoExpand': {
            'elements': 5000,
            'stringLength': 8192,
            'depth': 10,
        },
    },
}


# -----------------------------------------------------------------------------
# Type Definitions
# -----------------------------------------------------------------------------

@dataclass
class Spec:
    """Represents the current test specification being executed."""
    id: int = 0
    name: str = ''
    index: int = 0
    bit_position: int = 0
    # First range hit during this test
    first_file_id: Optional[int] = None
    first_range_id: Optional[int] = None
    # Last range hit during this test
    last_file_id: Optional[int] = None
    last_range_id: Optional[int] = None


@dataclass
class RangeHits:
    """Tracks hit counts for a specific code range."""
    count: int = 0
    spec_hits: Dict[int, Dict[str, int]] = field(default_factory=dict)


# -----------------------------------------------------------------------------
# Tracer Class
# -----------------------------------------------------------------------------

class Tracer:
    """
    Main tracer class for Python runtime instrumentation.
    
    Handles:
    - Coverage tracking
    - Console log interception
    - Value inspection and formatting
    - Test lifecycle events
    - Communication with parent process
    """
    
    def __init__(self, send_func: Callable[[Dict[str, Any]], None]):
        """
        Initialize the tracer.
        
        Args:
            send_func: Function to send messages to the parent process
        """
        self._send_func = send_func
        self._seq = 1
        self._session_id: Optional[str] = None
        self._child_session: Optional[str] = None
        
        # Test state
        self._spec = Spec()
        self._test_file_ids: Set[int] = set()
        self._spec_file_id: Optional[int] = None
        
        # Coverage tracking
        self._coverage: Dict[int, List[List[int]]] = {}
        
        # File encounter tracking
        self._file_encounter: Dict[int, int] = {}
        self._file_encounter_sequence: List[int] = []
        self._test_loading_sequence: List[Dict[str, Any]] = []
        
        # Console/log tracking
        self._console_hits: Dict[str, RangeHits] = {}
        self._auto_time_hits: Dict[str, Dict[str, Any]] = {}
        self._log_stats: Dict[str, Any] = {}
        
        # Trace context
        self._trace: Optional[Dict[str, Any]] = None
        self._trace_context: Optional[Dict[str, Any]] = None
        self._trace_stack_depth: int = 0
        self._trace_frame_scopes: Dict[int, int] = {}
        self._selected_tests: Optional[Any] = None
        self._trace_recording_enabled = True
        
        # Configuration
        self._log_limits = copy.deepcopy(DEFAULT_LOG_LIMITS)
        self._max_log_entry_size = MAX_LOG_ENTRY_SIZE
        self._max_trace_steps = MAX_TRACE_STEPS
        self._max_trace_steps_for_watch_expression_prefetch = MAX_TRACE_STEPS_FOR_WATCH_EXPRESSION_PREFETCH
        self._hints: Dict[str, Any] = {}
        self._auto_console_log = True
        self._capture_console_log = True
        
        # Expressions to evaluate
        self._expressions_to_evaluate: Dict[str, Any] = {}
        
        # State flags
        self._receiver_ready = False
        self._finished = False
        self._logging_value = False
        self._suppress_console_log = False
        
        # Pending actions queue (for when receiver not ready)
        self._pending_actions: List[Callable[[], None]] = []
        
        # Original console functions
        self._original_print = print
        
        # Intercept console output
        self._intercept_console()

    def set_log_limits(self, log_limits: Optional[Dict[str, Any]]) -> None:
        """Apply log limits configuration with validation and defaults."""
        defaults = copy.deepcopy(DEFAULT_LOG_LIMITS)

        if not isinstance(log_limits, dict):
            self._log_limits = defaults
            return

        def _coerce_positive(value: Any, fallback: int) -> int:
            if isinstance(value, (int, float)) and value > 0:
                return int(value)
            return fallback

        inline = log_limits.get('inline', {}) if isinstance(log_limits.get('inline'), dict) else {}
        values = log_limits.get('values', {}) if isinstance(log_limits.get('values'), dict) else {}
        values_default = values.get('default', {}) if isinstance(values.get('default'), dict) else {}
        values_auto = values.get('autoExpand', {}) if isinstance(values.get('autoExpand'), dict) else {}

        defaults['inline']['depth'] = _coerce_positive(inline.get('depth'), defaults['inline']['depth'])
        defaults['inline']['elements'] = _coerce_positive(inline.get('elements'), defaults['inline']['elements'])
        defaults['values']['default']['stringLength'] = _coerce_positive(
            values_default.get('stringLength'),
            defaults['values']['default']['stringLength'],
        )
        defaults['values']['autoExpand']['elements'] = _coerce_positive(
            values_auto.get('elements'),
            defaults['values']['autoExpand']['elements'],
        )
        defaults['values']['autoExpand']['stringLength'] = _coerce_positive(
            values_auto.get('stringLength'),
            defaults['values']['autoExpand']['stringLength'],
        )
        defaults['values']['autoExpand']['depth'] = _coerce_positive(
            values_auto.get('depth'),
            defaults['values']['autoExpand']['depth'],
        )

        self._log_limits = defaults

    def set_selected_tests(self, selected_tests: Optional[Any]) -> None:
        """Set the selected test filter for the current run."""
        self._selected_tests = selected_tests
    
    # -------------------------------------------------------------------------
    # Console Interception
    # -------------------------------------------------------------------------
    
    def _intercept_console(self) -> None:
        """Intercept Python print statements to capture console output."""
        tracer = self
        original_print = self._original_print
        
        def intercepted_print(*args, **kwargs):
            target_stream = kwargs.get('file')
            writes_to_console = target_stream is None or target_stream in (sys.stdout, sys.stderr)

            if not writes_to_console:
                original_print(*args, **kwargs)
                return

            if not tracer._suppress_console_log:
                # Capture the output
                tracer._do_when_receiver_ready(
                    lambda: tracer._log(*args)
                )
            # Still call original print if capture is disabled
            if not tracer._capture_console_log:
                original_print(*args, **kwargs)
        
        # Replace built-in print
        import builtins
        builtins.print = intercepted_print
    
    def restore_console(self) -> None:
        """Restore original print function."""
        import builtins
        builtins.print = self._original_print
    
    # -------------------------------------------------------------------------
    # Receiver Communication
    # -------------------------------------------------------------------------
    
    def set_receiver_ready(self) -> None:
        """Mark the receiver as ready and process pending actions."""
        self._receiver_ready = True
        for action in self._pending_actions:
            try:
                action()
            except Exception as e:
                self._send_global_error({
                    'message': str(e),
                    'stack': traceback.format_exc()
                })
        self._pending_actions.clear()
    
    def _do_when_receiver_ready(self, action: Callable[[], None]) -> None:
        """
        Execute action when receiver is ready, or queue it.
        
        Args:
            action: Callable to execute
        """
        if self._receiver_ready:
            action()
        else:
            self._pending_actions.append(action)
    
    def _send(self, msg_type: str, data: Any = None) -> None:
        """
        Send a message to the parent process.
        
        Args:
            msg_type: Type of message
            data: Message payload
        """
        message = self._create_message(msg_type, data)
        
        # Prevent recursion if send callback uses print()
        self._suppress_console_log = True
        try:
            self._send_func(message)
        finally:
            self._suppress_console_log = False
    
    def _create_message(self, msg_type: str, data: Any = None) -> Dict[str, Any]:
        """
        Create a message with standard fields.
        
        Args:
            msg_type: Type of message
            data: Message payload
            
        Returns:
            Complete message dictionary
        """
        msg = {
            'type': msg_type,
            'data': data,
            'session': self._session_id,
            'seq': self._get_next_seq(),
        }
        if self._child_session:
            msg['childSession'] = self._child_session
        return msg
    
    def _get_next_seq(self) -> int:
        """Get the next sequence number."""
        seq = self._seq
        self._seq += 1
        return seq
    
    # -------------------------------------------------------------------------
    # Session Management
    # -------------------------------------------------------------------------
    
    def set_session(self, session_id: str) -> None:
        """Set the current session ID."""
        self._session_id = session_id
    
    def reset(self) -> None:
        """Reset tracer state for a new test run."""
        # Coverage is reported per run. Keeping prior run buckets can remap
        # stale bits to new spec ids when ids restart from 1 in a new run.
        self._coverage.clear()
        self._console_hits.clear()
        self._auto_time_hits.clear()
        self._log_stats.clear()
        self._spec = Spec()
        self._trace = None
        self._trace_context = None
        self._trace_stack_depth = 0
        self._trace_frame_scopes = {}
        self._trace_recording_enabled = True
        self._reset_file_data()
    
    def _reset_file_data(self) -> None:
        """Reset file encounter data."""
        self._file_encounter.clear()
        self._file_encounter_sequence.clear()

    def init_trace(self, trace_context: Dict[str, Any]) -> None:
        """
        Initialize trace recording for time travel debugger.

        When trace is active, each statement() call records [fileId, rangeId, stackDepth]
        into the trace sequence, enabling step-by-step navigation.

        Args:
            trace_context: Trace configuration from the parent process, containing
                           'test' (the test to trace) and optional filters.
        """
        normalized_trace_context = dict(trace_context or {})
        steps = normalized_trace_context.get('stepsToRecordWatchExpressionsAt') or {}
        if isinstance(steps, dict):
            normalized_steps: Dict[int, bool] = {}
            for key, value in steps.items():
                try:
                    step = int(key)
                except (TypeError, ValueError):
                    continue
                normalized_steps[step] = bool(value)
            steps = normalized_steps
        else:
            steps = {}

        current_frame = normalized_trace_context.get('currentFrame')
        if not isinstance(current_frame, int) or current_frame < 0:
            current_frame = 0

        normalized_trace_context['currentFrame'] = current_frame
        normalized_trace_context['stepsToRecordWatchExpressionsAt'] = steps
        normalized_trace_context['allowRecordingValuesAttributtedToCurrentFrame'] = True
        normalized_trace_context['allowRecordingValues'] = True
        normalized_trace_context['allowedNumberOfStepsToRecordWatchExpressionsAfterCurrentStep'] = (
            self._max_trace_steps_for_watch_expression_prefetch
        )
        normalized_trace_context.pop('currentFrameStackDepth', None)

        self._trace_context = normalized_trace_context
        self._trace = {
            'sequence': [],
            'tests': {},
            'values': {},
        }
        self._trace_stack_depth = 0
        self._trace_frame_scopes = {}
        self._trace_recording_enabled = not self.has_spec_filter()
    
    def _reset_loading_data(self) -> None:
        """Reset test loading sequence data."""
        self._test_loading_sequence.clear()
    
    # -------------------------------------------------------------------------
    # Coverage Tracking
    # -------------------------------------------------------------------------
    
    def initialize_coverage(self, file_id: int, range_length: int) -> None:
        """
        Initialize coverage array for a file.
        
        Args:
            file_id: File identifier
            range_length: Number of coverage ranges in the file
        """
        if file_id not in self._coverage:
            self._coverage[file_id] = []
        
        file_coverage = self._coverage[file_id]
        while len(file_coverage) < range_length:
            file_coverage.append([])
    
    def statement(self, file_id: int, range_id: int) -> None:
        """
        Record that a statement was executed.
        
        Args:
            file_id: File identifier
            range_id: Range identifier within the file
        """
        # Track file encounter for result.files
        self.scope_start(file_id)
        
        # Track first range hit for this test
        if self._spec.first_file_id is None:
            self._spec.first_file_id = file_id
            self._spec.first_range_id = range_id
        
        # Always update last range hit
        self._spec.last_file_id = file_id
        self._spec.last_range_id = range_id
        
        # Record trace step for time travel debugger
        if self._trace is not None and self._trace_recording_enabled:
            sequence = self._trace['sequence']
            if len(sequence) < self._max_trace_steps:
                # Get scope ID for the calling frame to support step-over.
                # Like the JS tracer, we use a monotonic counter so each
                # unique function invocation gets its own ID.  We key on
                # the Python frame object identity which is unique per
                # invocation while the frame is alive.
                frame = sys._getframe(1)
                while frame is not None:
                    # Walk up past the adapter/runtime_globals frames
                    # to find the first user-code frame (one whose locals
                    # contain __runner_coverage__ or whose code object is
                    # from a known infrastructure file).
                    code_file = frame.f_code.co_filename
                    if 'wallaby_adapter' not in code_file and 'runtime_globals' not in code_file:
                        break
                    frame = frame.f_back
                if frame is not None:
                    frame_id = id(frame)
                    scope_id = self._trace_frame_scopes.get(frame_id)
                    if scope_id is None:
                        self._trace_stack_depth += 1
                        scope_id = self._trace_stack_depth
                        self._trace_frame_scopes[frame_id] = scope_id
                else:
                    scope_id = 0
                sequence.append([file_id, range_id, scope_id])
                self._record_trace_values(stack_depth=scope_id, from_logging_instruction=False)
        
        if file_id in self._coverage and range_id < len(self._coverage[file_id]):
            coverage = self._coverage[file_id][range_id]
            spec_index = self._spec.index
            bit_position = self._spec.bit_position
            
            # Ensure array is large enough
            while len(coverage) <= spec_index:
                coverage.append(0)
            
            # Set the bit for this spec
            coverage[spec_index] |= (1 << bit_position)

    def _clear_captured_trace_values(self) -> None:
        if self._trace is not None:
            self._trace['values'] = {}

    def _stop_trace_value_recording(self) -> None:
        self._clear_captured_trace_values()
        if self._trace_context is not None:
            self._trace_context['allowRecordingValues'] = False

    def _record_trace_values(self, stack_depth: int, from_logging_instruction: bool = False) -> None:
        trace_context = self._trace_context
        trace = self._trace
        if not trace_context or not trace:
            return
        if not trace_context.get('allowRecordingValues'):
            return

        sequence = trace.get('sequence') or []
        if not sequence:
            return

        active_frame = len(sequence) - 1
        current_frame = trace_context.get('currentFrame') or 0

        active_frame_is_after_current_frame = current_frame < active_frame
        current_frame_stack_depth = trace_context.get('currentFrameStackDepth')

        active_frame_is_after_current_frame_with_unknown_function_id = (
            active_frame_is_after_current_frame and not current_frame_stack_depth
        )

        active_frame_is_after_function_with_current_frame = (
            active_frame_is_after_current_frame_with_unknown_function_id
            or (current_frame_stack_depth and stack_depth < current_frame_stack_depth)
        )

        active_frame_is_after_or_in_function_with_current_frame = (
            active_frame_is_after_current_frame_with_unknown_function_id
            or (current_frame_stack_depth and stack_depth <= current_frame_stack_depth)
        )

        active_frame_is_after_current_frame_in_same_function = (
            bool(current_frame_stack_depth) and stack_depth == current_frame_stack_depth
        )

        steps_to_record_watch_expressions_at = trace_context.get('stepsToRecordWatchExpressionsAt') or {}
        active_frame_is_before_current_and_allowed_to_record = (
            active_frame < current_frame and bool(steps_to_record_watch_expressions_at.get(active_frame))
        )

        current_frame_is_active = current_frame == active_frame
        if current_frame_is_active and not from_logging_instruction:
            trace_context['currentFrameStackDepth'] = stack_depth

        if trace_context.get('allowRecordingValuesAttributtedToCurrentFrame') and (
            current_frame_is_active
            or (from_logging_instruction and active_frame_is_after_current_frame_in_same_function)
        ):
            self._record_captured_trace_values(current_frame, stack_depth)
        elif active_frame_is_before_current_and_allowed_to_record:
            self._record_captured_trace_values(active_frame, stack_depth)
        elif active_frame_is_after_current_frame_in_same_function:
            remaining_steps = trace_context.get(
                'allowedNumberOfStepsToRecordWatchExpressionsAfterCurrentStep',
                self._max_trace_steps_for_watch_expression_prefetch,
            )
            remaining_steps -= 1
            trace_context['allowedNumberOfStepsToRecordWatchExpressionsAfterCurrentStep'] = remaining_steps
            if remaining_steps < 0:
                self._stop_trace_value_recording()
            else:
                self._record_captured_trace_values(active_frame, stack_depth)

        if active_frame_is_after_or_in_function_with_current_frame:
            trace_context['allowRecordingValuesAttributtedToCurrentFrame'] = False

        if active_frame_is_after_function_with_current_frame:
            self._stop_trace_value_recording()

    def _record_captured_trace_values(self, frame: int, stack_depth: int) -> None:
        trace = self._trace
        if not trace:
            return

        values = trace.get('values') or {}
        if not values:
            return

        for expression_values in values.values():
            if not isinstance(expression_values, dict):
                continue

            value_entry: Optional[Dict[str, Any]] = None
            for key in reversed(list(expression_values.keys())):
                candidate = expression_values.get(key)
                if not isinstance(candidate, dict):
                    continue
                candidate_stack_depth = candidate.get('stackDepth')
                if isinstance(candidate_stack_depth, int) and candidate_stack_depth > stack_depth:
                    continue
                value_entry = candidate
                break

            if not value_entry:
                continue

            log_marker_context = {
                'changeId': value_entry.get('changeId'),
                'traceId': '*',
                'traceStep': frame,
                'preciseTraceStep': True,
                'initialTraceId': value_entry.get('traceId'),
            }

            self._emit_auto_log(
                file_id=value_entry.get('fileId'),
                range_id=value_entry.get('rangeId'),
                context=value_entry.get('context'),
                value=value_entry.get('value'),
                exp=value_entry.get('exp'),
                auto_expand=bool(value_entry.get('autoExpand')),
                change_id=log_marker_context.get('changeId'),
                trace_metadata=log_marker_context,
                spec_hit_count=-1 * frame,
                overall_hit_count=-1 * frame,
                increment_hits=False,
            )
    
    def scope_start(self, file_id: int) -> None:
        """
        Record that a file scope was entered.
        
        Args:
            file_id: File identifier
        """
        if file_id not in self._file_encounter:
            self._file_encounter_sequence.append(file_id)
            self._file_encounter[file_id] = 1
    
    def program_scope_start_loading(self, file_id: int) -> None:
        """Handle program scope start during loading phase."""
        if file_id in self._test_file_ids:
            self._spec_file_id = file_id
        self.scope_start(file_id)
    
    def program_scope_end_loading(self, file_id: int) -> None:
        """Handle program scope end during loading phase."""
        if file_id in self._test_file_ids:
            self._save_current_test_loading_sequence(file_id)
            self._reset_file_data()
    
    def _save_current_test_loading_sequence(self, test_file_id: int) -> None:
        """Save the loading sequence for a test file."""
        if self._file_encounter_sequence:
            self._test_loading_sequence.append({
                'testFileId': test_file_id,
                'fileIds': self._file_encounter_sequence.copy(),
            })
    
    def entry_file(self) -> Optional[int]:
        """Get the current spec file ID."""
        return self._spec_file_id
    
    # -------------------------------------------------------------------------
    # Test Lifecycle
    # -------------------------------------------------------------------------
    
    def init_loading_phase(self, test_files: List[Dict[str, Any]]) -> None:
        """
        Initialize the loading phase.
        
        Args:
            test_files: List of test file metadata
        """
        self._reset_loading_data()
        self._test_file_ids = {f.get('id') for f in test_files if f.get('id') is not None}
        self._seq = 1
    
    def started(self, data: Optional[Dict[str, Any]] = None) -> None:
        """
        Signal that test execution has started.
        
        Args:
            data: Additional data to include
        """
        data = data or {}
        data['loadingSequence'] = self._test_loading_sequence.copy()
        self._reset_loading_data()
        self._reset_file_data()
        self._send('started', data)
    
    def spec_start(self, spec_id: int, name: str, spec_file_id: int, path: List[str]) -> None:
        """
        Signal that a test spec has started.
        
        Args:
            spec_id: Unique spec identifier
            name: Test name
            spec_file_id: File containing the spec
            path: Path to the spec (suite hierarchy)
        """
        spec_name = name if isinstance(name, str) else self._inspect(name, 2, 10)
        
        self._do_when_receiver_ready(
            lambda: self._send('preTest', {
                'specName': spec_name,
                'specFileId': spec_file_id,
                'path': path
            })
        )
        
        self._spec = Spec(
            id=spec_id,
            name=spec_name,
            index=spec_id >> 5,
            bit_position=spec_id & 31,
        )
        
        if self._trace is not None:
            self._trace['tests'][spec_id] = {
                'start': len(self._trace['sequence'])
            }

    def set_spec_start_range(self, file_id: int, range_id: int) -> None:
        """
        Pre-set the starting range for the current spec.

        This allows the runner to associate the test with a specific
        declaration/body line even if setup hooks execute first.
        """
        if self._spec.first_file_id is None:
            self._spec.first_file_id = file_id
            self._spec.first_range_id = range_id
    
    def spec_sync_start(self) -> None:
        """Signal synchronous start of spec execution."""
        self._trace_recording_enabled = self._trace is not None

        if self._trace and self._spec.id:
            spec_entry = self._trace['tests'].get(self._spec.id)
            if spec_entry:
                spec_entry['start'] = len(self._trace['sequence'])
    
    def spec_sync_end(self) -> None:
        """Signal synchronous end of spec execution."""
        self._trace_recording_enabled = False
    
    def spec_end(self) -> Optional[List[int]]:
        """
        Signal that a test spec has ended.
        
        Returns:
            List of [first_file_id, first_range_id, last_file_id, last_range_id] or None
        """
        if self._trace:
            traced_spec = self._trace['tests'].get(self._spec.id)
            if traced_spec:
                traced_spec['end'] = max(
                    len(self._trace['sequence']) - 1,
                    traced_spec['start']
                )
                if traced_spec['start'] > len(self._trace['sequence']) - 1:
                    del self._trace['tests'][self._spec.id]

            self._trace_recording_enabled = False
        
        # Build test range: [first_file_id, first_range_id, last_file_id, last_range_id]
        test_range = None
        if self._spec.first_file_id is not None and self._spec.first_range_id is not None:
            test_range = [
                self._spec.first_file_id,
                self._spec.first_range_id,
                self._spec.last_file_id or self._spec.first_file_id,
                self._spec.last_range_id or self._spec.first_range_id,
            ]
        
        self._spec = Spec()
        
        return test_range
    
    def result(self, data: Dict[str, Any]) -> None:
        """
        Send test result.
        
        Args:
            data: Test result data
        """
        data['files'] = self._file_encounter_sequence
        self._reset_file_data()
        self._send('test', data)
    
    def set_assertion_data(self, failed_expectation: Dict[str, Any], log_entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich a log entry with assertion data from a failed expectation.
        
        This mirrors the JavaScript tracer's setAssertionData function,
        adding actual/expected values from assertions to the log entry.
        
        Args:
            failed_expectation: Dict with error/assertion info (may have actual, expected, etc.)
            log_entry: Dict with message and stack to enrich
            
        Returns:
            The enriched log entry
        """
        try:
            # Check for actual/expected values
            actual = failed_expectation.get('actual')
            expected = failed_expectation.get('expected')
            
            if actual is not None and expected is not None:
                # Format actual/expected for display
                actual_type = type(actual).__name__
                expected_type = type(expected).__name__
                
                # Only show diff for compatible types (not booleans, numbers, functions)
                if (actual_type == expected_type and 
                    actual_type not in ('bool', 'int', 'float', 'function')):
                    if not isinstance(actual, str):
                        log_entry['actual'] = self._inspect(actual, 5, 1000)
                        log_entry['expected'] = self._inspect(expected, 5, 1000)
                    else:
                        log_entry['actual'] = actual
                        log_entry['expected'] = expected
            
            # Add stack from actual error object if available
            if isinstance(actual, Exception) and hasattr(actual, '__traceback__'):
                import traceback as tb
                actual_stack = ''.join(tb.format_exception(type(actual), actual, actual.__traceback__))
                log_entry['stack'] = log_entry.get('stack', '') + '\nFrom actual error object:\n' + actual_stack
        except Exception:
            # Can't set actual and expected, continue without them
            pass
        
        return log_entry
    
    def setAssertionData(self, failed_expectation: Dict[str, Any], log_entry: Dict[str, Any]) -> Dict[str, Any]:
        """Alias for set_assertion_data to match JS tracer API."""
        return self.set_assertion_data(failed_expectation, log_entry)

    def logpoints_used(self, file_path: str, logpoints: List[str]) -> None:
        """Report used logpoints to the parent process."""
        self._do_when_receiver_ready(
            lambda: self._send('usedLogpoints', {'file': file_path, 'logpoints': logpoints})
        )

    def logpoint(
        self,
        file_id: int,
        range_id: int,
        logpoint_id: str,
        value: Any,
        context: Optional[str] = None,
    ) -> Any:
        """
        Log a logpoint value with location and changeId metadata.
        Returns the value so expressions preserve semantics.
        """
        def _action() -> None:
            self._emit_auto_log(
                file_id=file_id,
                range_id=range_id,
                context=context or 'logpoint',
                value=value,
                exp=None,
                auto_expand=True,
                change_id=logpoint_id,
            )

        self._do_when_receiver_ready(_action)
        return value

    def auto_log(
        self,
        file_id: int,
        range_id: int,
        value: Any,
        change_id: Optional[Any] = None,
        trace_id: Optional[Any] = None,
        exp: Optional[Any] = None,
        context: Optional[str] = None,
        auto_expand: bool = False,
    ) -> Any:
        """
        Log a Show Value (virtual log) entry with location and changeId metadata.
        Returns the value so expressions preserve semantics.
        """
        def _action() -> None:
            if trace_id is not None and self._trace is not None and self._trace_context is not None:
                self._capture_trace_value(
                    file_id=file_id,
                    range_id=range_id,
                    context=context or '',
                    value=value,
                    exp=exp,
                    change_id=change_id,
                    trace_id=trace_id,
                    auto_expand=auto_expand,
                )
                return

            self._emit_auto_log(
                file_id=file_id,
                range_id=range_id,
                context=context or '',
                value=value,
                exp=exp,
                auto_expand=auto_expand,
                change_id=change_id,
            )

        self._do_when_receiver_ready(_action)
        return value

    def auto_time(
        self,
        file_id: int,
        range_id: int,
        elapsed_ms: float,
        context: Optional[str] = None,
        log_marker_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a timed live-comment measurement for later emission."""

        def _action() -> None:
            file_range_id = f"{file_id},{range_id}"
            existing = self._auto_time_hits.get(file_range_id)
            if existing is None:
                self._auto_time_hits[file_range_id] = {
                    'value': elapsed_ms,
                    'context': context,
                    'fileId': file_id,
                    'rangeId': range_id,
                    'logMarkerContext': log_marker_context or {},
                }
                return

            if existing.get('n') is None:
                first = float(existing.get('value') or 0.0)
                existing['value'] = None
                existing['min'] = min(first, elapsed_ms)
                existing['max'] = max(first, elapsed_ms)
                existing['total'] = first + elapsed_ms
                existing['n'] = 2
                return

            existing['min'] = min(float(existing.get('min') or elapsed_ms), elapsed_ms)
            existing['max'] = max(float(existing.get('max') or elapsed_ms), elapsed_ms)
            existing['total'] = float(existing.get('total') or 0.0) + elapsed_ms
            existing['n'] = int(existing.get('n') or 0) + 1

        self._do_when_receiver_ready(_action)

    def _value_to_format(self, value: Any, exp: Optional[Any]) -> Any:
        if exp is None:
            return value

        if callable(exp):
            try:
                return exp(value)
            except TypeError:
                try:
                    return exp()
                except Exception:
                    return value
            except Exception:
                return value

        return value

    def _emit_auto_log(
        self,
        file_id: Optional[int],
        range_id: Optional[int],
        context: Optional[str],
        value: Any,
        exp: Optional[Any],
        auto_expand: bool,
        change_id: Optional[Any] = None,
        trace_metadata: Optional[Dict[str, Any]] = None,
        spec_hit_count: Optional[int] = None,
        overall_hit_count: Optional[int] = None,
        increment_hits: bool = True,
    ) -> None:
        if file_id is None or range_id is None:
            return

        file_range_id = f"{file_id},{range_id}"
        range_hits = self._get_range_hits(file_range_id)
        actual_spec_hit_count = (
            range_hits.spec_hits.get(self._spec.id, {}).get('count', 0)
            if spec_hit_count is None
            else spec_hit_count
        )
        actual_overall_hit_count = range_hits.count if overall_hit_count is None else overall_hit_count

        value_to_format = self._value_to_format(value, exp)
        expr_id = self._expression_id(file_id, file_range_id, actual_spec_hit_count, actual_overall_hit_count)
        value_bag = self._evaluate_expressions(expr_id, value_to_format, context or '', auto_expand=auto_expand)

        if change_id is not None or trace_metadata is not None:
            value_bag = value_bag or {}
            if change_id is not None:
                value_bag['changeId'] = change_id
            if trace_metadata is not None:
                value_bag.update(trace_metadata)

        if auto_expand and value_bag and value_bag.get('data'):
            value_bag['data']['autoExpand'] = True

        if increment_hits:
            range_hits.count += 1
            if self._spec.id not in range_hits.spec_hits:
                range_hits.spec_hits[self._spec.id] = {'count': 0}
            range_hits.spec_hits[self._spec.id]['count'] += 1

        # Keep auto-log payload JS-compatible: when valueBag is available,
        # let core format from serialized data (same path as console.log).
        data = {} if value_bag is not None else self._format(value_to_format)
        self._send_log('autoLog', data, context, file_id, range_id, value_bag)

    def _capture_trace_value(
        self,
        file_id: int,
        range_id: int,
        context: str,
        value: Any,
        exp: Optional[Any],
        change_id: Optional[Any],
        trace_id: Any,
        auto_expand: bool,
    ) -> None:
        trace = self._trace
        trace_context = self._trace_context
        if not trace or not trace_context:
            return

        sequence = trace.get('sequence') or []
        if not sequence:
            return

        active_frame = len(sequence) - 1
        current_frame = trace_context.get('currentFrame') or 0
        stack_depth = sequence[-1][2]
        expression_id = self._expression_id(file_id, f"{file_id},{range_id}", 0, 0)
        expression_values = trace['values'].setdefault(expression_id, {})
        expression_value_keys = list(expression_values.keys())
        if len(expression_value_keys) > 5:
            del expression_values[expression_value_keys[0]]

        expression_values[f'_{stack_depth}'] = {
            'fileId': file_id,
            'rangeId': range_id,
            'context': context,
            'value': value,
            'exp': exp,
            'changeId': change_id,
            'traceId': trace_id,
            'autoExpand': auto_expand,
            'stackDepth': stack_depth,
        }

        if active_frame >= current_frame:
            self._emit_auto_log(
                file_id=file_id,
                range_id=range_id,
                context=context,
                value=value,
                exp=exp,
                auto_expand=auto_expand,
                change_id=change_id,
                trace_metadata={
                    'traceId': '*',
                    'traceStep': current_frame,
                    'preciseTraceStep': True,
                    'initialTraceId': trace_id,
                },
                spec_hit_count=-1 * current_frame,
                overall_hit_count=-1 * current_frame,
                increment_hits=False,
            )

        self._record_trace_values(stack_depth=stack_depth, from_logging_instruction=True)
    
    def diff(self, *args) -> Any:
        """Return the last argument (mirrors JS tracer behavior)."""
        return args[-1] if args else None
    
    def complete(self, data: Optional[Dict[str, Any]] = None) -> None:
        """
        Signal that test execution is complete.
        
        Args:
            data: Completion data
        """
        self._send_coverage_and_time_measures()
        
        if self._trace:
            self._trace['values'] = {}
            self._send('trace', {'trace': self._trace})
            self._trace = None
        
        self._send('complete', data)
        self._finished = True
    
    def _send_coverage_and_time_measures(self) -> None:
        """Send coverage data and timing measurements."""
        # Send file-by-file coverage
        for file_id, file_coverage in self._coverage.items():
            if file_coverage:
                self._send('coverage', {'id': file_id, 'ranges': file_coverage})
        
        # Send timing data
        for range_id, range_time in self._auto_time_hits.items():
            if range_time.get('fileId') is not None:
                value_bag = None
                log_marker_context = range_time.get('logMarkerContext', {})
                
                if log_marker_context.get('traceId') or log_marker_context.get('changeId'):
                    value_bag = {
                        'traceId': log_marker_context.get('traceId'),
                        'changeId': log_marker_context.get('changeId'),
                        'traceStep': log_marker_context.get('traceStep'),
                        'preciseTraceStep': log_marker_context.get('preciseTraceStep'),
                        'initialTraceId': log_marker_context.get('initialTraceId'),
                    }
                    if log_marker_context.get('permanent'):
                        value_bag['permanent'] = True
                
                if range_time.get('value') is not None:
                    content = f"{range_time['value']:.3f}ms"
                else:
                    content = (
                        f"Σ {range_time['total']:.3f}ms"
                        f", μ {range_time['total'] / range_time['n']:.3f}ms"
                        f", ⋀ {range_time['min']:.3f}ms"
                        f", ⋁ {range_time['max']:.3f}ms"
                    )
                
                self._send_log(
                    'autoLog',
                    {'content': content, 'format': 'raw'},
                    range_time.get('context'),
                    range_time.get('fileId'),
                    range_time.get('rangeId'),
                    value_bag
                )
    
    # -------------------------------------------------------------------------
    # Error Reporting
    # -------------------------------------------------------------------------
    
    def report_global_error(self, error: Union[str, Exception, Dict[str, Any]]) -> None:
        """
        Report a global error.
        
        Args:
            error: Error to report
        """
        self._do_when_receiver_ready(
            lambda: self._send_global_error(error)
        )
    
    def _send_global_error(self, error: Union[str, Exception, Dict[str, Any]]) -> None:
        """Send global error message."""
        if isinstance(error, str):
            error_obj = {'message': error, 'stack': error}
        elif isinstance(error, Exception):
            error_obj = {
                'message': str(error),
                'stack': traceback.format_exc()
            }
        else:
            error_obj = error
        
        self._send('globalError', error_obj)
    
    def report_declaration_error(self, error: Exception) -> None:
        """Report a declaration error."""
        self._send('globalError', {
            'message': str(error),
            'stack': traceback.format_exc(),
            'declaration': True
        })
    
    # -------------------------------------------------------------------------
    # Transformed File Reporting
    # -------------------------------------------------------------------------
    
    def send_transformed_file(self, file_data: Dict[str, Any]) -> None:
        """
        Send transformed file information to the parent process.
        
        This notifies the core about the instrumented file's ranges,
        which is necessary for coverage indicators to work.
        
        Args:
            file_data: Dict matching RunnerTransformedFile type:
                - id: File ID (number or string)
                - transformed: Dict with optional 'map' (source map string)
                - instrumented: Dict with 'ranges' and optional fields
                - transformedTime: Timestamp string (ISO format)
                - lineMap: Optional line mapping
        """
        self._do_when_receiver_ready(
            lambda: self._send('transformedFile', file_data)
        )
    
    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------
    
    def _log(self, *args) -> None:
        """Handle console.log equivalent with valueBag for object inspection."""
        # Prevent recursion during value evaluation
        self._logging_value = True
        try:
            # Create valueBag for expandable object viewing
            value_bag = None
            if args and self._auto_console_log:
                try:
                    # For single argument, traverse it directly
                    # For multiple arguments, wrap in tuple
                    expression = args[0] if len(args) == 1 else args
                    
                    # Generate a simple expression ID for console logs
                    console_hit_key = 'console_log'
                    if console_hit_key not in self._console_hits:
                        self._console_hits[console_hit_key] = RangeHits()
                    hits = self._console_hits[console_hit_key]
                    expr_id = f"console,{hits.count}"
                    hits.count += 1
                    
                    value_bag = self._evaluate_expressions(expr_id, expression, 'print(...)', auto_expand=True)
                    if value_bag and value_bag.get('data'):
                        value_bag['data']['autoExpand'] = True
                except Exception:
                    # Don't let valueBag creation break logging
                    pass
            
            self._send_log(
                'log',
                self._format(*args),
                None, None, None, value_bag,
                stack=self._current_stack()
            )
        finally:
            self._logging_value = False
    
    def _warn(self, *args) -> None:
        """Handle console.warn equivalent."""
        self._send_log('warn', self._format(*args))
    
    def _error(self, *args) -> None:
        """Handle console.error equivalent."""
        self._send_log('error', self._format(*args))
    
    def _send_log(
        self,
        log_type: str,
        data: Dict[str, Any],
        context: Optional[str] = None,
        file_id: Optional[int] = None,
        range_id: Optional[int] = None,
        value_bag: Optional[Dict[str, Any]] = None,
        expected: Any = None,
        actual: Any = None,
        log_time: Optional[float] = None,
        stack: Optional[str] = None
    ) -> None:
        """
        Send a log message.
        
        Args:
            log_type: Type of log (log, warn, error, etc.)
            data: Log data with content and format
            context: Expression context
            file_id: Source file ID
            range_id: Source range ID
            value_bag: Evaluated value data
            expected: Expected value for assertions
            actual: Actual value for assertions
            log_time: Timestamp
            stack: Stack trace
        """
        content = data.get('content', '')
        length = len(content) if content else 0
        
        if content and length > self._max_log_entry_size:
            content = content[:self._max_log_entry_size] + f'...\n(truncated, total length: {length})'
            data = {'content': content, 'format': 'raw'}
        
        # Build message with only non-None values to match JS behavior
        # (JS uses undefined which gets omitted from JSON)
        message: Dict[str, Any] = {
            'type': log_type,
            'spec': self._spec.id,
            'time': log_time or int(time.time() * 1000),
        }
        
        # Only include optional fields if they have values
        if data.get('content') is not None:
            message['text'] = data.get('content')
        if data.get('format') is not None:
            message['format'] = data.get('format')
        if data.get('prefix') is not None:
            message['prefix'] = data.get('prefix')
        if value_bag is not None:
            message['valueBag'] = value_bag
        if file_id is not None:
            message['file'] = file_id
        if range_id is not None:
            message['range'] = range_id
        if context is not None:
            message['context'] = context
        if expected is not None:
            message['expected'] = expected
        if actual is not None:
            message['actual'] = actual
        if stack is not None:
            message['stack'] = stack
        
        self._send('console', message)
    
    def log(self, *args, context: Optional[str] = None, 
            file_id: Optional[int] = None, range_id: Optional[int] = None) -> None:
        """
        Log a value with location info.
        
        Args:
            *args: Values to log
            context: Expression context
            file_id: Source file ID
            range_id: Source range ID
        """
        self._do_when_receiver_ready(
            lambda: self._log_with_location(args, context, file_id, range_id)
        )
    
    def print_with_location(
        self,
        file_id: int,
        range_id: int,
        args: tuple,
        kwargs: dict,
        auto_expand: bool = None,
    ) -> None:
        """
        Handle print() calls from instrumented code with location info.
        
        This captures print calls and creates expandable object trees in the
        value viewer, similar to how JavaScript console.log is handled.
        
        Args:
            file_id: Source file ID
            range_id: Range ID for the print statement location
            args: Arguments passed to print()
            kwargs: Keyword arguments passed to print() (sep, end, file, flush)
            auto_expand: If explicitly set, override default auto-expand (True)
        """
        _debug_log(f'print_with_location called: file_id={file_id}, range_id={range_id}, args={args}')
        # Create a context string from the print arguments
        context = 'print(...)'
        
        # Only deep-expand when auto_expand was explicitly set (e.g. #?+ magic comment),
        # not when it was defaulted to True for regular print() calls.
        deep_auto_expand = auto_expand is True
        
        # Default to auto-expand for print output (matches JS console.log behavior)
        if auto_expand is None:
            auto_expand = True
        
        # Queue the log action
        self._do_when_receiver_ready(
            lambda: self._print_with_location_impl(file_id, range_id, args, kwargs, context, auto_expand, deep_auto_expand)
        )
        _debug_log(f'print_with_location: queued _print_with_location_impl')
    
    def _print_with_location_impl(
        self,
        file_id: int,
        range_id: int,
        args: tuple,
        kwargs: dict,
        context: str,
        auto_expand: bool = True,
        deep_auto_expand: bool = False,
    ) -> None:
        """Implementation of print_with_location."""
        _debug_log(f'_print_with_location_impl called: file_id={file_id}, range_id={range_id}')
        
        # Prevent recursion during value evaluation
        self._logging_value = True
        try:
            file_range_id = f"{file_id},{range_id}"
            range_hits = self._get_range_hits(file_range_id)
            overall_hit_count = range_hits.count
            spec_hit_count = range_hits.spec_hits.get(self._spec.id, {}).get('count', 0)
            _debug_log(f'_print_with_location_impl: overall_hit_count={overall_hit_count}, spec_hit_count={spec_hit_count}')
            
            value_bag = None
            
            # For print statements, we want to traverse all arguments
            # If there's a single argument, traverse it directly
            # If there are multiple arguments, create an array-like structure
            if len(args) == 0:
                expression = ''
            elif len(args) == 1:
                expression = args[0]
            else:
                # Multiple arguments - we'll traverse each one
                expression = args
            
            if overall_hit_count < EVALUATED_EXPRESSION_PER_RANGE_LIMIT:
                expr_id = self._expression_id(file_id, file_range_id, spec_hit_count, overall_hit_count)
                value_bag = self._evaluate_expressions(expr_id, expression, context, auto_expand=auto_expand, deep_auto_expand=deep_auto_expand)
                
                # Mark as auto-expand so the value viewer expands by default
                if auto_expand and value_bag and value_bag.get('data'):
                    value_bag['data']['autoExpand'] = True
            
            range_hits.count += 1
            if self._spec.id not in range_hits.spec_hits:
                range_hits.spec_hits[self._spec.id] = {'count': 0}
            range_hits.spec_hits[self._spec.id]['count'] += 1
            
            # Send as 'log' type (like JavaScript console.log) for display in Tests Output panel
            # Use valueBag for expandable object viewing
            _debug_log(f'_print_with_location_impl: sending log with value_bag={value_bag is not None}')
            self._send_log('log', {}, context, file_id, range_id, value_bag)
            _debug_log(f'_print_with_location_impl: _send_log completed')
        finally:
            self._logging_value = False
    
    def _log_with_location(
        self, 
        args: tuple, 
        context: Optional[str],
        file_id: Optional[int],
        range_id: Optional[int]
    ) -> None:
        """Log with file/range location."""
        if file_id is None or range_id is None:
            self._log(*args)
            return
        
        file_range_id = f"{file_id},{range_id}"
        range_hits = self._get_range_hits(file_range_id)
        overall_hit_count = range_hits.count
        spec_hit_count = range_hits.spec_hits.get(self._spec.id, {}).get('count', 0)
        
        value_bag = None
        expression = args[0] if len(args) == 1 else args
        
        if overall_hit_count < EVALUATED_EXPRESSION_PER_RANGE_LIMIT:
            value_bag = self._evaluate_expressions(
                self._expression_id(file_id, file_range_id, spec_hit_count, overall_hit_count),
                expression,
                context
            )
        
        range_hits.count += 1
        if self._spec.id not in range_hits.spec_hits:
            range_hits.spec_hits[self._spec.id] = {'count': 0}
        range_hits.spec_hits[self._spec.id]['count'] += 1
        
        if value_bag:
            self._send_log('log', {}, context, file_id, range_id, value_bag)
    
    def _get_range_hits(self, file_range_id: str) -> RangeHits:
        """Get or create range hits tracking."""
        if file_range_id not in self._console_hits:
            self._console_hits[file_range_id] = RangeHits()
        return self._console_hits[file_range_id]
    
    def _expression_id(
        self, 
        file_id: int, 
        file_range_id: str, 
        spec_hit_count: int, 
        overall_hit_count: int,
        proxy_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate a unique expression ID."""
        entry_file_id = str(self.entry_file() or '')
        file_id_str = str(file_id)
        
        expr_id = f"{file_range_id},{overall_hit_count}"
        if entry_file_id != file_id_str:
            expr_id += f",{entry_file_id}"
        
        if proxy_data:
            expr_id += f"#{proxy_data.get('overallHitCount', 0)}"
        
        return expr_id
    
    # -------------------------------------------------------------------------
    # Value Formatting and Inspection
    # -------------------------------------------------------------------------
    
    def _format(self, *args) -> Dict[str, str]:
        """
        Format arguments for logging.
        
        Args:
            *args: Values to format
            
        Returns:
            Dict with 'content' and optionally 'format' keys
        """
        if not args:
            return {'content': ''}
        
        depth = self._log_limits['inline']['depth']
        max_elements = self._log_limits['inline']['elements']
        
        formatted = []
        for arg in args:
            formatted.append(self._inspect(arg, depth, max_elements))
        
        return {'content': ' '.join(formatted)}
    
    def _inspect(
        self, 
        obj: Any, 
        depth: int = 5, 
        max_elements: int = 5000,
        hide_types: bool = False,
        sort_properties: bool = False,
        resolve_getters: bool = False
    ) -> str:
        """
        Inspect and format an object for display.
        
        Args:
            obj: Object to inspect
            depth: Maximum recursion depth
            max_elements: Maximum elements per level
            hide_types: Whether to hide type annotations
            sort_properties: Whether to sort object properties
            resolve_getters: Whether to resolve property getters
            
        Returns:
            Formatted string representation
        """
        seen: Set[int] = set()
        return self._format_value(obj, depth, max_elements, seen)
    
    def _format_value(
        self, 
        obj: Any, 
        depth: int, 
        max_elements: int, 
        seen: Set[int]
    ) -> str:
        """Format a value recursively."""
        if obj is UNDEFINED:
            return 'undefined'

        # Handle primitives
        if obj is None:
            return 'null'
        
        obj_type = type(obj).__name__
        
        if isinstance(obj, bool):
            return str(obj)
        
        if isinstance(obj, int) and not isinstance(obj, bool):
            return str(obj)

        if isinstance(obj, float):
            return str(obj)
        
        if isinstance(obj, str):
            # Escape and quote strings
            escaped = obj.replace("'", "\\'")
            return f"'{escaped}'"
        
        if isinstance(obj, (bytes, bytearray)):
            return f"Buffer({len(obj)})"
        
        # Check for circular references
        obj_id = id(obj)
        if obj_id in seen:
            return '[Circular]'
        
        # Check depth limit
        if depth <= 0:
            if isinstance(obj, dict):
                return '{...}'
            elif isinstance(obj, (list, tuple)):
                return '[...]' if isinstance(obj, list) else '(...)'
            else:
                return f'[{obj_type}]'
        
        seen.add(obj_id)
        
        try:
            if isinstance(obj, dict):
                if not obj:
                    return '{}'
                items = []
                for i, (k, v) in enumerate(obj.items()):
                    if i >= max_elements:
                        items.append('...')
                        break
                    key_str = self._format_value(k, depth - 1, max_elements, seen)
                    val_str = self._format_value(v, depth - 1, max_elements, seen)
                    items.append(f'{key_str}: {val_str}')
                return '{ ' + ', '.join(items) + ' }'
            
            if isinstance(obj, (list, tuple)):
                if not obj:
                    return '[]' if isinstance(obj, list) else '()'
                items = []
                for i, item in enumerate(obj):
                    if i >= max_elements:
                        items.append('...')
                        break
                    items.append(self._format_value(item, depth - 1, max_elements, seen))
                brackets = '[]' if isinstance(obj, list) else '()'
                return brackets[0] + ' ' + ', '.join(items) + ' ' + brackets[1]
            
            if isinstance(obj, set):
                if not obj:
                    return 'set()'
                items = []
                for i, item in enumerate(obj):
                    if i >= max_elements:
                        items.append('...')
                        break
                    items.append(self._format_value(item, depth - 1, max_elements, seen))
                return '{ ' + ', '.join(items) + ' }'
            
            if isinstance(obj, type):
                return f'<class {obj.__name__}>'
            
            if callable(obj):
                name = getattr(obj, '__name__', 'anonymous')
                return f'[λ: {name}]'
            
            if isinstance(obj, Exception):
                return f'[{obj_type}: {str(obj)}]'
            
            # Try to use repr for other objects
            try:
                repr_str = repr(obj)
                if len(repr_str) > 100:
                    repr_str = repr_str[:100] + '...'
                return repr_str
            except Exception:
                return f'[{obj_type}]'
        
        finally:
            seen.discard(obj_id)
    
    def _evaluate_expressions(
        self,
        expr_id: str,
        value: Any,
        context: Optional[str],
        error: Optional[Exception] = None,
        auto_expand: bool = False,
        deep_auto_expand: bool = False,
    ) -> Dict[str, Any]:
        """
        Evaluate and format an expression for the value viewer.
        
        Args:
            expr_id: Expression identifier
            value: Value to evaluate
            context: Expression context
            error: Optional error to report
            
        Returns:
            Value bag with evaluation result
        """
        result = {}
        expression_runtime_key = self._expression_runtime_key(expr_id)

        try:
            if error:
                result['data'] = {'error': str(error), 'id': expr_id}
                result['data']['queryPath'] = [expr_id]
                result['data']['expressionPath'] = [context] if context is not None else []
                result['expressionRuntimeKey'] = expression_runtime_key
            else:
                inline_limits = self._log_limits.get('inline', {})
                values_limits = self._log_limits.get('values', {})
                default_limits = values_limits.get('default', {})
                auto_limits = values_limits.get('autoExpand', {})

                if auto_expand:
                    # Match JS tracer behavior: initial auto-expand traversal starts at
                    # depth=2 and uses autoExpand string limits, but propagates
                    # auto-expand context so nested objects are expanded up to
                    # autoExpandMaxDepth.
                    depth = 2
                    max_elements = inline_limits.get('elements', 5000)
                    string_length = auto_limits.get('stringLength', default_limits.get('stringLength', 8192))
                    auto_expand_max_depth = auto_limits.get('depth', 10)
                    auto_expand_limit = auto_limits.get('elements', 5000)
                else:
                    depth = inline_limits.get('depth', 5)
                    max_elements = inline_limits.get('elements', 5000)
                    string_length = default_limits.get('stringLength', 8192)
                    auto_expand_max_depth = 10
                    auto_expand_limit = 5000

                expression_path = [context] if context is not None else None
                expressions_to_evaluate = self._lookup_expressions_to_evaluate(expr_id)

                result['data'] = self._traverse_object(
                    value,
                    context,
                    depth=depth,
                    max_elements=max_elements,
                    string_length=string_length,
                    expression_id=expr_id,
                    query_path=[expr_id],
                    expression_path=expression_path,
                    expressions_to_evaluate=expressions_to_evaluate,
                    node_indices=[],
                    auto_expand=deep_auto_expand,
                    auto_expand_max_depth=auto_expand_max_depth,
                    auto_expand_limit=auto_expand_limit,
                )
                result['data']['id'] = expr_id

                # Preserve a stable runtime key for value re-evaluation/expansion.
                result['expressionRuntimeKey'] = expression_runtime_key
        except Exception as e:
            result['data'] = {'error': f'Error evaluating "{context}": {str(e)}', 'id': expr_id}
            result['data']['queryPath'] = [expr_id]
            result['data']['expressionPath'] = [context] if context is not None else []
            result['expressionRuntimeKey'] = expression_runtime_key

        return result

    def _expression_runtime_key(self, expr_id: str) -> str:
        """Create a stable runtime key independent of per-run hit counts."""
        key = expr_id

        # Keep parity with server-side key derivation.
        if key.endswith(',valueContainer'):
            key = key[:key.rfind(',')]
        elif '#' in key:
            key = key[:key.rfind('#')]

        parts = key.split(',')
        if len(parts) >= 3:
            parts.pop(2)

        return ','.join(parts)

    def _lookup_expressions_to_evaluate(self, expr_id: str) -> Optional[Dict[str, Any]]:
        """Resolve expressions-to-evaluate map for an expression id."""
        if not isinstance(self._expressions_to_evaluate, dict):
            return None

        expression_runtime_key = self._expression_runtime_key(expr_id)
        candidates: List[str] = [expression_runtime_key, expr_id]
        candidates.append(expression_runtime_key + ',')
        candidates.append(expr_id + ',')
        if expression_runtime_key.endswith(','):
            candidates.append(expression_runtime_key.rstrip(','))
        if expr_id.endswith(','):
            candidates.append(expr_id.rstrip(','))
        if '#' in expr_id:
            candidates.append(expr_id.split('#', 1)[0])

        if '#' in expression_runtime_key:
            candidates.append(expression_runtime_key.split('#', 1)[0])

        seen: Set[str] = set()
        for key in candidates:
            if key in seen:
                continue
            seen.add(key)
            if key in self._expressions_to_evaluate:
                value = self._expressions_to_evaluate.get(key)
                if isinstance(value, dict):
                    return value
                return {}

        return None

    def _property_accessor(self, name: str) -> str:
        """Create a JS-like property accessor for expressionPath."""
        if name.isdigit():
            return f'[{name}]'
        if IDENTIFIER_PROPERTY_PATTERN.match(name):
            return f'.{name}'
        return f'[{json.dumps(name)}]'

    def _node_id(self, expression_id: str, node_indices: List[int]) -> str:
        if not node_indices:
            return expression_id
        return expression_id + ' ' + ' '.join(str(index) for index in node_indices)

    def _append_load_action_node(self, result: Dict[str, Any], query_path: List[str]) -> None:
        if not result.get('props'):
            return
        if not (result.get('cappedProps') or result.get('cappedElements')):
            return

        node_id = result.get('id') or (query_path[0] if query_path else 'value')
        result['props'].append({
            'loadActionNode': True,
            'id': f'{node_id} l',
            'queryPath': list(query_path),
            'label': {'name': '...'},
            'expandable': True,
            'disallowToCopyPath': True,
            'disallowToCopyData': True,
        })
    
    def _traverse_object(
        self,
        obj: Any,
        context: Optional[str] = None,
        depth: int = 5,
        max_props: int = 100,
        max_elements: int = 5000,
        string_length: int = 8192,
        expression_id: Optional[str] = None,
        query_path: Optional[List[str]] = None,
        expression_path: Optional[List[str]] = None,
        expressions_to_evaluate: Optional[Dict[str, Any]] = None,
        node_indices: Optional[List[int]] = None,
        auto_expand: bool = False,
        auto_expand_max_depth: int = 10,
        auto_expand_level: int = 0,
        auto_expand_property_count: Optional[List[int]] = None,
        auto_expand_limit: int = 5000,
    ) -> Dict[str, Any]:
        """
        Traverse and serialize an object for the value viewer.
        
        Args:
            obj: Object to traverse
            context: Expression context
            depth: Maximum depth
            max_props: Maximum properties
            max_elements: Maximum array elements
            
        Returns:
            Serialized object structure
        """
        obj_type = self._get_type_name(obj)
        result: Dict[str, Any] = {'type': obj_type}
        node_indices = node_indices or []
        query_path = list(query_path or [])
        if auto_expand_property_count is None:
            auto_expand_property_count = [0]

        if expression_id:
            result['id'] = self._node_id(expression_id, node_indices)
        if query_path:
            result['queryPath'] = query_path
        if expression_path is not None:
            result['expressionPath'] = list(expression_path)

        requested_children = expressions_to_evaluate if isinstance(expressions_to_evaluate, dict) else None

        should_auto_expand = (
            auto_expand
            and auto_expand_level < auto_expand_max_depth
            and not callable(obj)
            and auto_expand_property_count[0] < auto_expand_limit
        )

        def get_child_request(name: str) -> Optional[Dict[str, Any]]:
            if requested_children is None:
                return None
            child_request = requested_children.get(f'_p_{name}')
            return child_request if isinstance(child_request, dict) else ({} if child_request is not None else None)

        def get_child_depth(child_request: Optional[Dict[str, Any]]) -> int:
            child_depth = depth - 1
            if child_request is not None and child_depth < 1:
                child_depth = 1
            return child_depth

        auto_expand_child_kwargs = {
            'auto_expand': auto_expand,
            'auto_expand_max_depth': auto_expand_max_depth,
            'auto_expand_level': auto_expand_level + 1,
            'auto_expand_property_count': auto_expand_property_count,
            'auto_expand_limit': auto_expand_limit,
        } if should_auto_expand else {}

        def finalize(node: Dict[str, Any]) -> Dict[str, Any]:
            self._append_load_action_node(node, query_path)
            if node.get('props') or node.get('capped') or node.get('cappedProps') or node.get('cappedElements'):
                node['expandable'] = True
            return node

        if obj is UNDEFINED:
            result['type'] = 'undefined'
            result['value'] = 'undefined'
            return result
        
        # Handle primitives
        if obj is None:
            result['value'] = 'null'
            return result
        
        if isinstance(obj, bool):
            result['value'] = obj
            return result
        
        if isinstance(obj, int) and not isinstance(obj, bool):
            result['value'] = obj
            return result

        if isinstance(obj, float):
            result['value'] = obj
            # Handle special numeric values
            if obj != obj:  # NaN check
                result['nan'] = True
                del result['value']
            elif obj == float('inf'):
                result['positiveInfinity'] = True
                del result['value']
            elif obj == float('-inf'):
                result['negativeInfinity'] = True
                del result['value']
            return result
        
        if isinstance(obj, str):
            result['value'] = obj
            result['length'] = len(obj)
            if len(obj) > string_length:
                result['capped'] = obj[:string_length]
                del result['value']
            return finalize(result)
        
        if isinstance(obj, (bytes, bytearray)):
            result['type'] = 'Buffer'
            result['length'] = len(obj)
            if (depth > 0 or should_auto_expand or requested_children is not None) and obj:
                result['props'] = []
                for i, item in enumerate(list(obj)[:max_elements]):
                    child_name = str(i)
                    child_request = get_child_request(child_name)
                    child_expression_path = (
                        expression_path + [self._property_accessor(child_name)] if expression_path is not None else None
                    )
                    auto_expand_property_count[0] += 1
                    prop = self._traverse_object(
                        item,
                        child_name,
                        get_child_depth(child_request),
                        max_props,
                        max_elements,
                        string_length,
                        expression_id=expression_id,
                        query_path=query_path + [f'_p_{child_name}'],
                        expression_path=child_expression_path,
                        expressions_to_evaluate=child_request,
                        node_indices=node_indices + [i],
                        **auto_expand_child_kwargs,
                    )
                    prop['name'] = child_name
                    result['props'].append(prop)
                if len(obj) > max_elements:
                    result['cappedElements'] = True
            elif obj:
                result['capped'] = True
            return finalize(result)

        # Handle collections
        if isinstance(obj, (list, tuple)):
            result['length'] = len(obj)
            if (depth > 0 or should_auto_expand or requested_children is not None) and obj:
                result['props'] = []
                for i, item in enumerate(obj[:max_elements]):
                    child_name = str(i)
                    child_request = get_child_request(child_name)
                    child_expression_path = (
                        expression_path + [self._property_accessor(child_name)] if expression_path is not None else None
                    )
                    auto_expand_property_count[0] += 1
                    prop = self._traverse_object(
                        item,
                        child_name,
                        get_child_depth(child_request),
                        max_props,
                        max_elements,
                        string_length,
                        expression_id=expression_id,
                        query_path=query_path + [f'_p_{child_name}'],
                        expression_path=child_expression_path,
                        expressions_to_evaluate=child_request,
                        node_indices=node_indices + [i],
                        **auto_expand_child_kwargs,
                    )
                    prop['name'] = child_name
                    result['props'].append(prop)
                if len(obj) > max_elements:
                    result['cappedElements'] = True
            elif obj:
                result['capped'] = True
            return finalize(result)
        
        if isinstance(obj, dict):
            if (depth > 0 or should_auto_expand or requested_children is not None) and obj:
                result['props'] = []
                for i, (k, v) in enumerate(list(obj.items())[:max_props]):
                    child_name = str(k)
                    child_request = get_child_request(child_name)
                    child_expression_path = (
                        expression_path + [self._property_accessor(child_name)] if expression_path is not None else None
                    )
                    auto_expand_property_count[0] += 1
                    prop = self._traverse_object(
                        v,
                        child_name,
                        get_child_depth(child_request),
                        max_props,
                        max_elements,
                        string_length,
                        expression_id=expression_id,
                        query_path=query_path + [f'_p_{child_name}'],
                        expression_path=child_expression_path,
                        expressions_to_evaluate=child_request,
                        node_indices=node_indices + [i],
                        **auto_expand_child_kwargs,
                    )
                    prop['name'] = child_name
                    result['props'].append(prop)
                if len(obj) > max_props:
                    result['cappedProps'] = True
            elif obj:
                result['capped'] = True
            return finalize(result)
        
        if isinstance(obj, set):
            result['length'] = len(obj)
            if (depth > 0 or should_auto_expand or requested_children is not None) and obj:
                result['props'] = []
                for i, item in enumerate(list(obj)[:max_elements]):
                    child_name = str(i)
                    child_request = get_child_request(child_name)
                    child_expression_path = (
                        expression_path + [self._property_accessor(child_name)] if expression_path is not None else None
                    )
                    auto_expand_property_count[0] += 1
                    prop = self._traverse_object(
                        item,
                        child_name,
                        get_child_depth(child_request),
                        max_props,
                        max_elements,
                        string_length,
                        expression_id=expression_id,
                        query_path=query_path + [f'_p_{child_name}'],
                        expression_path=child_expression_path,
                        expressions_to_evaluate=child_request,
                        node_indices=node_indices + [i],
                        **auto_expand_child_kwargs,
                    )
                    prop['name'] = child_name
                    result['props'].append(prop)
                if len(obj) > max_elements:
                    result['cappedElements'] = True
            elif obj:
                result['capped'] = True
            return finalize(result)
        
        # Handle callable objects
        if callable(obj):
            name = getattr(obj, '__name__', 'anonymous')
            result['value'] = f'λ: {name}'
            return result
        
        # Handle exceptions
        if isinstance(obj, Exception):
            result['value'] = str(obj)
            return result
        
        # Handle other objects by inspecting attributes
        if depth > 0 or should_auto_expand or requested_children is not None:
            result['props'] = []
            try:
                attr_names_all = [k for k in dir(obj) if not k.startswith('_')]
                attr_names = attr_names_all[:max_props]
                for i, name in enumerate(attr_names):
                    try:
                        val = getattr(obj, name)
                    except Exception:
                        continue
                    if not callable(val):
                        child_request = get_child_request(name)
                        child_expression_path = (
                            expression_path + [self._property_accessor(name)] if expression_path is not None else None
                        )
                        auto_expand_property_count[0] += 1
                        prop = self._traverse_object(
                            val,
                            name,
                            get_child_depth(child_request),
                            max_props,
                            max_elements,
                            string_length,
                            expression_id=expression_id,
                            query_path=query_path + [f'_p_{name}'],
                            expression_path=child_expression_path,
                            expressions_to_evaluate=child_request,
                            node_indices=node_indices + [i],
                            **auto_expand_child_kwargs,
                        )
                        prop['name'] = name
                        result['props'].append(prop)
                if len(attr_names_all) > max_props:
                    result['cappedProps'] = True
            except Exception:
                pass
        else:
            result['capped'] = True

        return finalize(result)
    
    def _get_type_name(self, obj: Any) -> str:
        """Get the type name for an object."""
        if obj is None:
            return 'null'
        if obj is UNDEFINED:
            return 'undefined'
        
        obj_type = type(obj).__name__
        
        if obj_type == 'NoneType':
            return 'null'
        elif obj_type == 'str':
            return 'string'
        elif obj_type == 'int':
            return 'number'
        elif obj_type == 'float':
            return 'number'
        elif obj_type == 'bool':
            return 'boolean'
        elif obj_type == 'list':
            return 'array'
        elif obj_type == 'dict':
            return 'object'
        elif obj_type == 'tuple':
            return 'tuple'
        elif obj_type == 'set':
            return 'Set'
        elif obj_type == 'bytes' or obj_type == 'bytearray':
            return 'Buffer'
        elif obj_type == 'frozenset':
            return 'FrozenSet'
        elif callable(obj):
            return 'function'
        else:
            return obj_type

    def _current_stack(self) -> str:
        """Get the current call stack."""
        return ''.join(traceback.format_stack()[:-2])
    
    # -------------------------------------------------------------------------
    # Run Received Notification
    # -------------------------------------------------------------------------
    
    def run_received(self) -> None:
        """Notify that run configuration was received."""
        self._send('runReceived', {})
    
    # -------------------------------------------------------------------------
    # Spec Filtering
    # -------------------------------------------------------------------------
    
    def has_spec_filter(self) -> bool:
        """Check if there's a spec filter active."""
        return bool(self._selected_tests and self._selected_tests != '*')
    
    def spec_filter(self, path: List[str]) -> bool:
        """
        Check if a spec matches the current filter.
        
        Args:
            path: Path to the spec (suite/test hierarchy)
            
        Returns:
            True if spec should run, False otherwise
        """
        tests = self._selected_tests
        if not tests:
            return True
        
        if tests == '*':
            return True
        
        # Check for test name without suite pattern
        test_names_without_suite = tests.get(':?')
        if test_names_without_suite and test_names_without_suite.get(':' + path[-1]):
            return True
        
        # Check full path pattern
        suite = tests
        for part in path:
            suite = suite.get(':' + part)
            if not suite:
                return False
            if suite == '*':
                return True
        
        return False


# -----------------------------------------------------------------------------
# Global Tracer Instance Management
# -----------------------------------------------------------------------------

_tracer: Optional[Tracer] = None


def get_tracer() -> Optional[Tracer]:
    """Get the global tracer instance."""
    return _tracer


def init_tracer(send_func: Callable[[Dict[str, Any]], None]) -> Tracer:
    """
    Initialize the global tracer.
    
    Args:
        send_func: Function to send messages to parent process
        
    Returns:
        The initialized tracer instance
    """
    global _tracer
    _tracer = Tracer(send_func)
    return _tracer


def destroy_tracer() -> None:
    """Destroy the global tracer and restore console."""
    global _tracer
    if _tracer:
        _tracer.restore_console()
        _tracer = None


_wallaby_original_init_trace = Tracer.init_trace
_wallaby_original_statement = Tracer.statement


def _wallaby_init_trace_with_call_stack(self, trace_context):
    _wallaby_original_init_trace(self, trace_context)

    capture_frame = (trace_context or {}).get('captureCallStackFrame')
    if isinstance(capture_frame, int) and capture_frame >= 0 and self._trace_context is not None:
        self._trace_context['captureCallStackFrame'] = capture_frame
    elif self._trace_context is not None:
        self._trace_context.pop('captureCallStackFrame', None)


def _wallaby_statement_with_call_stack(self, file_id, range_id):
    captured_stack = None
    if self._trace and self._trace_context:
        capture_frame = self._trace_context.get('captureCallStackFrame')
        next_frame = len(self._trace.get('sequence') or [])
        if capture_frame == next_frame:
            captured_stack = self._current_stack()

    _wallaby_original_statement(self, file_id, range_id)

    if captured_stack is None or not self._trace or not self._trace_context:
        return

    capture_frame = self._trace_context.get('captureCallStackFrame')
    self._trace['callStack'] = self._trace.get('callStack') or {}
    self._trace['callStack'][capture_frame] = {'stack': captured_stack}


Tracer.init_trace = _wallaby_init_trace_with_call_stack
Tracer.statement = _wallaby_statement_with_call_stack
