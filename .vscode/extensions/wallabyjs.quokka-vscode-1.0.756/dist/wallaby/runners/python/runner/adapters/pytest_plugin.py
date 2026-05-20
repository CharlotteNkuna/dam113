from __future__ import annotations

"""
Pytest plugin for code instrumentation.

This plugin integrates the instrumentation session with pytest, allowing
coverage tracking, value logging, and source mapping while using pytest
as the test runner.

Usage:
    # In conftest.py or as a pytest plugin
    from runner.adapters.pytest_plugin import InstrumentedTestPlugin
    
    def pytest_configure(config):
        plugin = InstrumentedTestPlugin(project_root="/path/to/project")
        config.pluginmanager.register(plugin, "instrumented_test_plugin")

Or programmatically:
    from runner.adapters.pytest_plugin import run_pytest_instrumented
    
    result = run_pytest_instrumented(
        project_root="/path/to/project",
        pytest_args=["tests/", "-v"],
    )
"""

import inspect
import contextlib
import pytest
import time
import sys
import types
import importlib
import importlib.machinery
import traceback
from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from pathlib import Path

from _pytest import hookspec as pytest_hookspec
try:
    from _pytest.skipping import evaluate_skip_marks as pytest_evaluate_skip_marks
except Exception:
    pytest_evaluate_skip_marks = None

from ..import_resolution import resolve_module_import_context
from ..session import InstrumentationSession, InstrumentationConfig


class InstrumentedModule(pytest.Module):
    """
    Custom Module collector that uses our pre-instrumented module.
    
    The standard pytest.Module._getobj() calls importtestmodule() which
    reimports the module from the file path, bypassing our instrumented
    version in sys.modules. This subclass overrides _getobj() to return
    the already-instrumented module instead.
    """
    
    # Class-level registry mapping file paths to instrumented modules
    _instrumented_modules: dict[str, types.ModuleType] = {}
    
    @classmethod
    def register_instrumented_module(cls, path: str, module: types.ModuleType) -> None:
        """Register an instrumented module for a file path."""
        cls._instrumented_modules[str(Path(path).resolve())] = module
    
    @classmethod
    def get_instrumented_module(cls, path: str) -> Optional[types.ModuleType]:
        """Get the instrumented module for a file path."""
        return cls._instrumented_modules.get(str(Path(path).resolve()))
    
    def _getobj(self) -> types.ModuleType:
        """
        Return our pre-instrumented module instead of reimporting.
        
        This is the key fix: pytest's default _getobj() calls importtestmodule()
        which reimports from the file, losing our instrumentation. By returning
        the module we already executed, we ensure tests run with instrumented code.
        """
        path_str = str(self.path.resolve())
        module = self._instrumented_modules.get(path_str)
        if module is not None:
            return module
        # Fall back to default behavior if not found (shouldn't happen)
        return super()._getobj()
from ..runtime_globals import TimeLog, ValueLog
from ..source_map import SourceMap
from ..events import (
    EventEmitter,
    EventType,
    TestInfo,
    TestsCollectedEvent,
    TestFileStartEvent,
    TestFileEndEvent,
    TestStartEvent,
    TestEndEvent,
    TestResult,
    InstrumentationEvent,
)


def _spec_filter(test_names: dict[str, Any], path: list[str]) -> bool:
    if not path:
        return False

    test_names_without_suite = test_names.get(':?')
    if isinstance(test_names_without_suite, dict) and test_names_without_suite.get(':' + path[-1]):
        return True

    suite: Any = test_names
    for part in path:
        if not isinstance(suite, dict):
            return suite == '*'

        suite = suite.get(':' + part)
        if not suite:
            return False
        if suite == '*':
            return True

    return False


def _get_pycollect_makemodule_hook_arg_name() -> str:
    """Return the pytest collection hook argument name for the installed version."""
    parameters = inspect.signature(pytest_hookspec.pytest_pycollect_makemodule).parameters
    if 'module_path' in parameters:
        return 'module_path'
    return 'path'


_PYCOLLECT_MAKEMODULE_HOOK_ARG_NAME = _get_pycollect_makemodule_hook_arg_name()


def _get_pytest_major_version() -> int:
    raw_version = getattr(pytest, '__version__', '0')
    try:
        return int(str(raw_version).split('.', 1)[0])
    except Exception:
        return 0


_PYTEST_MAJOR_VERSION = _get_pytest_major_version()


def _loaded_project_module_paths(project_root: Path) -> list[str]:
    project_root = project_root.resolve()
    loaded_paths: list[str] = []
    seen_paths: set[str] = set()

    for name, module in list(sys.modules.items()):
        module_file = getattr(module, '__file__', None)
        if not module_file:
            module_spec = getattr(module, '__spec__', None)
            module_file = getattr(module_spec, 'origin', None) if module_spec else None
        if not module_file or module_file in ('built-in', 'frozen') or module_file.startswith('<'):
            continue

        try:
            module_path = Path(module_file).resolve()
        except Exception:
            continue

        module_path_str = str(module_path)
        if '/.venv/' in module_path_str or '/venv/' in module_path_str or '/site-packages/' in module_path_str:
            continue

        try:
            if module_path.is_relative_to(project_root):
                resolved_path = str(module_path)
                if resolved_path not in seen_paths:
                    seen_paths.add(resolved_path)
                    loaded_paths.append(resolved_path)
        except Exception:
            if module_path_str.startswith(str(project_root)):
                if module_path_str not in seen_paths:
                    seen_paths.add(module_path_str)
                    loaded_paths.append(module_path_str)

    return loaded_paths


@dataclass
class TestItemData:
    """Data captured for a single test item."""
    
    nodeid: str
    file_path: str
    test_name: str
    line_number: int
    covered_lines: dict[str, set[int]] = field(default_factory=dict)
    value_logs: list[ValueLog] = field(default_factory=list)
    result: TestResult = TestResult.PASSED
    passed: bool = True
    error: Optional[str] = None
    error_traceback: Optional[str] = None
    assertion_actual: Optional[str] = None
    assertion_expected: Optional[str] = None
    duration_ms: float = 0.0
    start_time: float = field(default=0.0, repr=False)
    finalized: bool = False


@dataclass
class TestFileData:
    """Data captured for a test file."""
    
    path: str
    test_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    duration_ms: float = 0.0
    start_time: float = field(default=0.0, repr=False)


class InstrumentedTestPlugin:
    """
    Pytest plugin that instruments code during test execution.
    
    This plugin:
    - Installs import hooks before test collection
    - Tracks per-test coverage data
    - Captures runtime value logs
    - Provides source map translation for errors
    - Emits lifecycle events for file/test execution
    """
    
    def __init__(
        self,
        project_root: str,
        enable_coverage: bool = True,
        enable_value_logging: bool = True,
        selected_tests: Optional[dict[str, Any] | str] = None,
        include_paths: Optional[list[str]] = None,
        exclude_paths: Optional[list[str]] = None,
        hints: Optional[dict[str, Any]] = None,
        on_coverage_hit: Optional[Callable[[str, int], None]] = None,
        on_value_logged: Optional[Callable[[ValueLog], None]] = None,
        on_time_logged: Optional[Callable[[TimeLog], None]] = None,
        on_test_call_start: Optional[Callable[[str], None]] = None,
        on_print_called: Optional[Callable[[str, int, tuple, dict], None]] = None,
        on_logpoint_called: Optional[Callable[[str, int, str, Any], None]] = None,
        on_loading_complete: Optional[Callable[[], None]] = None,
        log: Optional[Callable[[str], None]] = None,
    ):
        self._log = log or (lambda msg: None)  # No-op if no log function provided
        
        hints = hints or {}
        self.config = InstrumentationConfig(
            project_root=project_root,
            enable_coverage=enable_coverage,
            enable_value_logging=enable_value_logging,
            rewrite_asserts=True,
            include_paths=include_paths or ["src", "tests"],
            exclude_paths=exclude_paths or [".venv", "venv", "node_modules", "__pycache__"],
            ignore_coverage=hints.get("ignoreCoverage"),
            ignore_coverage_for_file=hints.get("ignoreCoverageForFile"),
        )
        
        self.session = InstrumentationSession(
            config=self.config,
            on_coverage_hit=on_coverage_hit,
            on_value_logged=on_value_logged,
            on_time_logged=on_time_logged,
            on_print_called=on_print_called,
            on_logpoint_called=on_logpoint_called,
        )
        self._on_test_call_start = on_test_call_start
        self._on_loading_complete = on_loading_complete
        self._selected_tests = selected_tests
        
        # Per-test tracking
        self._current_test: Optional[str] = None
        self._current_test_start_time: float = 0.0
        self._pre_test_coverage: dict[str, set[int]] = {}
        self._pre_test_log_count: int = 0
        self._test_data: dict[str, TestItemData] = {}
        self._pending_test_outcomes: dict[str, TestResult] = {}
        self._collected_test_infos: dict[str, TestInfo] = {}
        self._last_assertion_compare: Optional[tuple[str, object, object]] = None
        
        # Per-file tracking
        self._current_file: Optional[str] = None
        self._file_data: dict[str, TestFileData] = {}
        self._managed_sys_path_entries: list[str] = []
    
    @property
    def events(self) -> EventEmitter:
        """Get the event emitter (shared with session)."""
        return self.session.events
    
    @property
    def test_data(self) -> dict[str, TestItemData]:
        """Get captured data for all tests."""
        return self._test_data
    
    @property
    def file_data(self) -> dict[str, TestFileData]:
        """Get captured data for all test files."""
        return self._file_data
    
    @property
    def coverage(self):
        """Get overall coverage data."""
        return self.session.coverage
    
    def get_source_map(self, path: str) -> Optional[SourceMap]:
        """Get source map for a file."""
        return self.session.get_source_map(path)

    def _create_instrumented_module_collector(
        self,
        parent: pytest.Collector,
        module_path: Path,
    ) -> pytest.Module:
        try:
            return InstrumentedModule.from_parent(parent, path=module_path)
        except TypeError as error:
            if 'fspath' not in str(error):
                raise
            try:
                import py

                return InstrumentedModule.from_parent(parent, fspath=py.path.local(str(module_path)))
            except ImportError:
                return InstrumentedModule.from_parent(parent, fspath=module_path)

    def _prepend_sys_path_entry(self, path: str) -> None:
        resolved = str(Path(path).resolve())
        if not sys.path or resolved != sys.path[0]:
            sys.path.insert(0, resolved)
            self._managed_sys_path_entries.append(resolved)

    def _translate_traceback(self, tb_text: str) -> str:
        """Translate line numbers in a traceback to original source lines."""
        lines = tb_text.splitlines()
        translated_lines = []

        for line in lines:
            if 'File "' in line and '", line ' in line:
                try:
                    start = line.index('File "') + 6
                    end = line.index('", line ')
                    path = line[start:end]

                    line_start = end + 8
                    line_end = line.find(",", line_start)
                    if line_end == -1:
                        line_end = len(line)
                    line_num = int(line[line_start:line_end].strip())

                    source_map = self.get_source_map(path)
                    if source_map:
                        original_line = source_map.translate_traceback_line(line_num)
                        if original_line != line_num:
                            line = line[:line_start] + str(original_line) + line[line_end:]
                except (ValueError, IndexError):
                    pass
            translated_lines.append(line)

        return "\n".join(translated_lines)
    
    def _get_test_file_path(self, item: pytest.Item) -> str:
        """Get the file path from a test item."""
        return str(Path(item.fspath).resolve()) if hasattr(item, 'fspath') else str(item.path.resolve())
    
    def _get_test_name(self, item: pytest.Item) -> str:
        """Get human-readable test name."""
        return item.name
    
    def _get_test_line(self, item: pytest.Item) -> int:
        """Get the line number where the test is defined."""
        test_object = getattr(item, 'function', None) or getattr(item, 'obj', None)
        if test_object is not None:
            try:
                source_lines, start_line = inspect.getsourcelines(test_object)
                for offset, source_line in enumerate(source_lines):
                    stripped = source_line.lstrip()
                    if stripped.startswith('def ') or stripped.startswith('async def '):
                        return start_line + offset
            except (OSError, IOError, TypeError):
                pass

            if hasattr(test_object, '__code__'):
                return test_object.__code__.co_firstlineno

        location = getattr(item, 'location', None)
        if location and len(location) > 1:
            return int(location[1]) + 1

        return 0

    def _selected_test_path(self, item: pytest.Item) -> list[str]:
        test_name = self._get_test_name(item)
        parts = item.nodeid.split('::')[1:]
        if not parts:
            return [test_name]

        parts[-1] = test_name
        return parts

    def _should_run_item(self, item: pytest.Item) -> bool:
        if not isinstance(self._selected_tests, dict) or not self._selected_tests:
            return True

        return _spec_filter(self._selected_tests, self._selected_test_path(item))
    
    # --- Pytest Hooks ---
    
    def pytest_configure(self, config: pytest.Config) -> None:
        """Called before test collection begins."""
        self._log('PytestPlugin: pytest_configure called')
        # Start session if not already started (e.g., when used via conftest)
        if not self.session._started:
            self._log('PytestPlugin: starting session from pytest_configure')
            self.session.start()
        else:
            self._log('PytestPlugin: session already started')
        
        # Store config for later use
        self._config = config
        self._instrumented_modules: set[str] = set()

    def pytest_collection_modifyitems(
        self,
        session: pytest.Session,
        config: pytest.Config,
        items: list[pytest.Item],
    ) -> None:
        if not isinstance(self._selected_tests, dict) or not self._selected_tests:
            return

        selected_items: list[pytest.Item] = []
        deselected_items: list[pytest.Item] = []

        for item in items:
            if self._should_run_item(item):
                selected_items.append(item)
            else:
                deselected_items.append(item)

        if not deselected_items:
            return

        items[:] = selected_items
        config.hook.pytest_deselected(items=deselected_items)
        self._log(
            'PytestPlugin: filtered collection to '
            f'{len(selected_items)} selected tests, deselected {len(deselected_items)} others'
        )
    
    def _pytest_pycollect_makemodule_impl(self, module_path: Path, parent: pytest.Collector) -> Optional[pytest.Module]:
        """
        Called before pytest creates a module from a test file.
        
        We use this to ensure test files go through our transformation pipeline.
        By importing the module through our import hook (which is installed in
        sys.meta_path), the test file gets instrumented.
        """
        module_path = Path(str(module_path))
        self._log(f'PytestPlugin: pytest_pycollect_makemodule called for {module_path}')

        if _PYTEST_MAJOR_VERSION and _PYTEST_MAJOR_VERSION < 7:
            self._log(f'PytestPlugin: using default collection path for legacy pytest on {module_path}')
            return None
        
        if not self.session._started:
            self._log(f'PytestPlugin: session not started, skipping {module_path}')
            return None
        
        # Convert path to module name
        path_str = str(module_path.resolve())
        
        # Check if this file should be instrumented
        if not self.session.config.should_instrument(path_str):
            self._log(f'PytestPlugin: should not instrument {path_str}')
            return None
        
        # Skip if already processed
        if path_str in self._instrumented_modules:
            self._log(f'PytestPlugin: already instrumented {path_str}')
            return None
        
        project_root = Path(self.session.config.project_root).resolve()
        import_context = resolve_module_import_context(module_path, project_root)
        module_name = import_context.module_name
        self._log(f'PytestPlugin: module_name={module_name}, sys_path_entry={import_context.sys_path_entry}')
        
        # Read and transform the test file directly using our interceptor
        loading_started = False
        try:
            preloaded_project_paths = _loaded_project_module_paths(project_root)
            self.events.emit(TestFileStartEvent(path=path_str, test_count=0))
            loading_started = True

            if self.session.interceptor.on_file_loaded:
                for loaded_path in preloaded_project_paths:
                    if loaded_path != path_str:
                        self.session.interceptor.on_file_loaded(loaded_path)

            content = self.session.interceptor.get_content(path_str)
            self._log(f'PytestPlugin: got content for {path_str}, len={len(content)}')
            
            # Emit file loaded event
            if self.session.interceptor.on_file_loaded:
                self.session.interceptor.on_file_loaded(path_str)
            
            # Transform and cache the source
            transformed, source_map, code = self.session.interceptor.transform_and_cache(path_str, content)
            self._log(f'PytestPlugin: transformed {path_str}, range_count={source_map.range_count}')
            
            # Debug: Log first 500 chars of transformed code to verify instrumentation
            self._log(f'PytestPlugin: transformed code preview:\n{transformed[:500]}...')
            
            # Remove from sys.modules if already imported (force reimport)
            if module_name in sys.modules:
                del sys.modules[module_name]
            
            # Create and execute the module
            import types
            module = types.ModuleType(module_name)
            module.__file__ = path_str
            module.__loader__ = None
            module.__package__ = import_context.package_name
            module.__spec__ = importlib.machinery.ModuleSpec(module_name, None, origin=path_str)
            
            sys.modules[module_name] = module

            self._prepend_sys_path_entry(import_context.sys_path_entry)
            exec(code, module.__dict__)
            
            self._instrumented_modules.add(path_str)
            self._log(f'PytestPlugin: successfully instrumented {path_str}')
            
            # Register the instrumented module so InstrumentedModule._getobj() can find it
            InstrumentedModule.register_instrumented_module(path_str, module)
            
            # Return our custom Module subclass that will use the instrumented module
            # instead of reimporting from the file
            return self._create_instrumented_module_collector(parent, module_path)
        except Exception as e:
            import traceback

            if self.session.on_transform_error:
                try:
                    self.session.on_transform_error(path_str, e, content)
                except Exception as callback_error:
                    self._log(f'PytestPlugin: error reporting transform failure for {path_str}: {callback_error}')
            if self.session.on_exec_error:
                try:
                    self.session.on_exec_error(path_str, e)
                except Exception as callback_error:
                    self._log(f'PytestPlugin: error reporting exec failure for {path_str}: {callback_error}')

            tracer = getattr(getattr(self.session, 'event_adapter', None), '_tracer', None)
            if tracer and not self.session.on_transform_error and not self.session.on_exec_error:
                try:
                    translated_traceback = self._translate_traceback(traceback.format_exc())
                    rel_path = self._normalize_path(path_str)
                    tracer.report_global_error(
                        {
                            'message': f'Failed to instrument {rel_path}: {e}',
                            'stack': translated_traceback,
                        }
                    )
                except Exception as callback_error:
                    self._log(f'PytestPlugin: error reporting tracer failure for {path_str}: {callback_error}')
            # Log the error and fall back to default behavior
            self._log(f'PytestPlugin: error instrumenting {path_str}: {e}')
            self._log(f'PytestPlugin: traceback: {traceback.format_exc()}')
        finally:
            if loading_started:
                self.events.emit(TestFileEndEvent(path=path_str))
        
        return None
    
    def pytest_unconfigure(self, config: pytest.Config) -> None:
        """Called after all tests have completed."""
        # Finalize any open file tracking
        self._finalize_current_file()

        for managed_path in reversed(self._managed_sys_path_entries):
            with contextlib.suppress(ValueError):
                sys.path.remove(managed_path)
        self._managed_sys_path_entries.clear()
        
        # Stop session if still running
        if self.session._started:
            self.session.stop()
    
    def pytest_runtest_setup(self, item: pytest.Item) -> None:
        """Called before each test runs."""
        file_path = self._get_test_file_path(item)
        test_name = self._get_test_name(item)
        line_number = self._get_test_line(item)
        test_data = self._ensure_test_started(
            nodeid=item.nodeid,
            file_path=file_path,
            test_name=test_name,
            line_number=line_number,
        )

        if pytest_evaluate_skip_marks is not None:
            try:
                skip_result = pytest_evaluate_skip_marks(item)
            except Exception:
                skip_result = None
            if skip_result is not None:
                test_data.result = TestResult.SKIPPED
                test_data.passed = True
                test_data.error = getattr(skip_result, 'reason', None)
                test_data.error_traceback = None
    
    def pytest_runtest_teardown(self, item: pytest.Item) -> None:
        """Called after each test completes."""
        self._finalize_test(item.nodeid)

    def _ensure_test_started(
        self,
        *,
        nodeid: str,
        file_path: str,
        test_name: str,
        line_number: int,
    ) -> TestItemData:
        test_data = self._test_data.get(nodeid)
        if test_data is not None:
            return test_data

        if self._current_file != file_path:
            self._finalize_current_file()
            self._current_file = file_path

        file_data = self._file_data.get(file_path)
        if file_data is None:
            file_data = TestFileData(
                path=file_path,
                start_time=time.perf_counter(),
            )
            self._file_data[file_path] = file_data

        file_data.test_count += 1

        self._current_test = nodeid
        self._current_test_start_time = time.perf_counter()
        self._pre_test_coverage = self.session.get_coverage_snapshot()
        self._pre_test_log_count = len(self.session.value_logs)

        test_data = TestItemData(
            nodeid=nodeid,
            file_path=file_path,
            test_name=test_name,
            line_number=line_number,
            start_time=self._current_test_start_time,
        )
        self._test_data[nodeid] = test_data

        self.events.emit(TestStartEvent(
            test_id=nodeid,
            test_name=test_name,
            file_path=file_path,
            line_number=line_number,
        ))

        return test_data

    def _finalize_test(self, nodeid: str) -> None:
        if nodeid not in self._test_data:
            return

        test_data = self._test_data[nodeid]
        if test_data.finalized:
            return

        test_data.finalized = True
        pending_result = self._pending_test_outcomes.pop(nodeid, None)
        if pending_result is not None:
            test_data.result = pending_result
            test_data.passed = True
            test_data.error = None
            test_data.error_traceback = None

        test_data.duration_ms = (time.perf_counter() - test_data.start_time) * 1000

        lines_covered = 0
        if self.session.coverage:
            for file, ranges in self.session.coverage.executed_ranges.items():
                pre_ranges = self._pre_test_coverage.get(file, set())
                new_ranges = ranges - pre_ranges
                if new_ranges:
                    test_data.covered_lines[file] = new_ranges
                    lines_covered += len(new_ranges)

        test_data.value_logs = self.session.value_logs[self._pre_test_log_count:]

        self.events.emit(TestEndEvent(
            test_id=nodeid,
            test_name=test_data.test_name,
            file_path=test_data.file_path,
            result=test_data.result,
            duration_ms=test_data.duration_ms,
            error_message=test_data.error,
            error_traceback=test_data.error_traceback,
            assertion_actual=test_data.assertion_actual,
            assertion_expected=test_data.assertion_expected,
            lines_covered=lines_covered,
        ))

        file_data = self._file_data.get(test_data.file_path)
        if file_data:
            if test_data.result == TestResult.PASSED:
                file_data.passed_count += 1
            elif test_data.result in (TestResult.SKIPPED, TestResult.XFAILED):
                file_data.skipped_count += 1
            elif test_data.result == TestResult.ERROR:
                file_data.error_count += 1
            else:
                file_data.failed_count += 1

        if self._current_test == nodeid:
            self._current_test = None

    def pytest_runtest_call(self, item: pytest.Item) -> None:
        """Called when pytest enters the test function body."""
        if self._on_test_call_start:
            self._on_test_call_start(item.nodeid)
    
    def pytest_assertrepr_compare(self, config, op: str, left, right):
        """Capture assertion comparison operands for diff display."""
        import pprint
        try:
            self._last_assertion_compare = (
                op,
                pprint.pformat(left),
                pprint.pformat(right),
            )
        except Exception:
            self._last_assertion_compare = None
        return None

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call: pytest.CallInfo):
        """Called to create test report - capture pass/fail status."""
        outcome = yield
        report = outcome.get_result()

        if item.nodeid not in self._test_data:
            return

        test_data = self._test_data[item.nodeid]

        if report.skipped:
            test_data.result = TestResult.XFAILED if getattr(report, 'wasxfail', False) else TestResult.SKIPPED
            test_data.passed = True
            test_data.error = None
            test_data.error_traceback = None
            self._last_assertion_compare = None
            return

        if report.when != "call":
            return

        if call.excinfo is not None:
            test_data.result = TestResult.FAILED
            test_data.passed = False
            test_data.error = str(call.excinfo.value)
            tb_text = "".join(traceback.format_exception(call.excinfo.type, call.excinfo.value, call.excinfo.tb))
            test_data.error_traceback = self._translate_traceback(tb_text)
            if (
                self._last_assertion_compare is not None
                and call.excinfo.errisinstance(AssertionError)
            ):
                _, actual_repr, expected_repr = self._last_assertion_compare
                test_data.assertion_actual = actual_repr
                test_data.assertion_expected = expected_repr
        else:
            test_data.result = TestResult.PASSED

        self._last_assertion_compare = None

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if not report.skipped:
            return

        test_data = self._test_data.get(report.nodeid)
        if test_data is None:
            collected_test = self._collected_test_infos.get(report.nodeid)
            if collected_test is not None:
                test_data = self._ensure_test_started(
                    nodeid=report.nodeid,
                    file_path=collected_test.file_path,
                    test_name=collected_test.test_name,
                    line_number=collected_test.line_number,
                )

        result = TestResult.XFAILED if getattr(report, 'wasxfail', False) else TestResult.SKIPPED
        self._pending_test_outcomes[report.nodeid] = result

        if test_data is not None:
            test_data.result = result
            test_data.passed = True
            test_data.error = getattr(report, 'longreprtext', None) or None
            test_data.error_traceback = None

        if report.when == 'setup':
            self._finalize_test(report.nodeid)
    
    def pytest_collection_finish(self, session: pytest.Session) -> None:
        """Called after collection is complete - emit collected tests event."""
        # Build list of all tests that will run
        test_infos = []
        file_test_counts: dict[str, int] = {}
        
        for item in session.items:
            file_path = self._get_test_file_path(item)
            file_test_counts[file_path] = file_test_counts.get(file_path, 0) + 1
            
            test_infos.append(TestInfo(
                test_id=item.nodeid,
                test_name=self._get_test_name(item),
                file_path=file_path,
                line_number=self._get_test_line(item),
            ))
        
        # Store for later use in test file start events
        self._file_test_counts = file_test_counts
        self._collected_test_infos = {test_info.test_id: test_info for test_info in test_infos}
        
        # Emit tests collected event
        self.events.emit(TestsCollectedEvent(tests=test_infos))
        if self._on_loading_complete:
            self._on_loading_complete()
    
    def _finalize_current_file(self) -> None:
        """Finalize tracking for the current test file."""
        if self._current_file and self._current_file in self._file_data:
            file_data = self._file_data[self._current_file]
            file_data.duration_ms = (time.perf_counter() - file_data.start_time) * 1000
            
            self._current_file = None
    
    def pytest_exception_interact(
        self,
        node: pytest.Item,
        call: pytest.CallInfo,
        report: pytest.TestReport,
    ) -> None:
        """Called when an exception is raised - could translate line numbers here."""
        # Note: For full traceback translation, you'd need to modify the
        # traceback before it's displayed. This is more complex and may
        # require patching pytest's reporting.
        pass


def run_pytest_instrumented(
    project_root: str,
    pytest_args: Optional[list[str]] = None,
    enable_coverage: bool = True,
    enable_value_logging: bool = True,
    include_paths: Optional[list[str]] = None,
    exclude_paths: Optional[list[str]] = None,
    on_coverage_hit: Optional[Callable[[str, int], None]] = None,
    on_value_logged: Optional[Callable[[ValueLog], None]] = None,
    on_time_logged: Optional[Callable[[TimeLog], None]] = None,
    on_logpoint_called: Optional[Callable[[str, int, str, Any], None]] = None,
) -> tuple[int, InstrumentedTestPlugin]:
    """
    Run pytest with instrumentation enabled.
    
    Args:
        project_root: Root directory of the project
        pytest_args: Arguments to pass to pytest (default: [])
        enable_coverage: Enable coverage tracking
        enable_value_logging: Enable value logging
        include_paths: Paths to instrument
        exclude_paths: Paths to exclude
        on_coverage_hit: Callback for coverage hits
        on_value_logged: Callback for logged values
    
    Returns:
        Tuple of (pytest exit code, plugin instance with captured data)
    
    Example:
        exit_code, plugin = run_pytest_instrumented(
            project_root="/path/to/project",
            pytest_args=["tests/", "-v"],
        )
        
        # Access coverage data
        print(f"Coverage: {plugin.coverage.get_coverage_percent():.1f}%")
        
        # Access per-test data
        for nodeid, data in plugin.test_data.items():
            print(f"{nodeid}: {'PASSED' if data.passed else 'FAILED'}")
    """
    plugin = InstrumentedTestPlugin(
        project_root=project_root,
        enable_coverage=enable_coverage,
        enable_value_logging=enable_value_logging,
        include_paths=include_paths,
        exclude_paths=exclude_paths,
        on_coverage_hit=on_coverage_hit,
        on_value_logged=on_value_logged,
        on_time_logged=on_time_logged,
        on_logpoint_called=on_logpoint_called,
    )
    
    # Start instrumentation BEFORE pytest runs (before module imports)
    plugin.session.start()
    
    try:
        # Run pytest with our plugin
        exit_code = pytest.main(
            pytest_args or [],
            plugins=[plugin],
        )
    finally:
        # Ensure cleanup happens
        plugin.session.stop()
    
    return exit_code, plugin


if _PYCOLLECT_MAKEMODULE_HOOK_ARG_NAME == 'module_path':

    @pytest.hookimpl(tryfirst=True)
    def _pytest_pycollect_makemodule(
        self: InstrumentedTestPlugin,
        module_path: Path,
        parent: pytest.Collector,
    ) -> Optional[pytest.Module]:
        return self._pytest_pycollect_makemodule_impl(module_path, parent)

else:

    @pytest.hookimpl(tryfirst=True)
    def _pytest_pycollect_makemodule(
        self: InstrumentedTestPlugin,
        path: Path,
        parent: pytest.Collector,
    ) -> Optional[pytest.Module]:
        return self._pytest_pycollect_makemodule_impl(path, parent)


setattr(InstrumentedTestPlugin, 'pytest_pycollect_makemodule', _pytest_pycollect_makemodule)


def create_conftest_plugin(
    project_root: str,
    **kwargs: Any,
) -> InstrumentedTestPlugin:
    """
    Create a plugin instance for use in conftest.py.
    
    Usage in conftest.py:
        from runner.adapters.pytest_plugin import create_conftest_plugin
        
        _plugin = create_conftest_plugin(
            project_root=str(Path(__file__).parent),
            enable_coverage=True,
        )
        
        def pytest_configure(config):
            config.pluginmanager.register(_plugin, "instrumentation")
        
        def pytest_unconfigure(config):
            # Access coverage data
            print(f"Coverage: {_plugin.coverage.get_coverage_percent():.1f}%")
    """
    return InstrumentedTestPlugin(project_root=project_root, **kwargs)
