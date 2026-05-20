"""
unittest adapter for instrumentation.

This adapter integrates the instrumentation session with Python's built-in
unittest runner while emitting the same lifecycle events consumed by the
Wallaby event adapter.
"""

from __future__ import annotations

import inspect
import importlib.util
import hashlib
import sys
import time
import traceback
import types
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from ..import_resolution import ModuleImportContext, resolve_module_import_context
from ..events import (
    EventEmitter,
    TestEndEvent,
    TestFileEndEvent,
    TestFileStartEvent,
    TestInfo,
    TestResult,
    TestsCollectedEvent,
    TestStartEvent,
)
from ..runtime_globals import TimeLog, ValueLog
from ..session import InstrumentationConfig, InstrumentationSession
from ..source_map import SourceMap


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


@dataclass
class TestItemData:
    test_id: str
    test_name: str
    file_path: str
    line_number: int
    start_time: float
    pre_test_coverage: dict[str, set[int]]
    pre_test_log_count: int
    result: TestResult = TestResult.PASSED
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None
    duration_ms: float = 0.0
    value_logs: list[ValueLog] = field(default_factory=list)


@dataclass
class TestFileData:
    path: str
    start_time: float
    passed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    duration_ms: float = 0.0


class _WallabyLoadErrorTestCase(unittest.TestCase):
    """Synthetic test that surfaces module load errors as test errors."""

    def __init__(self, file_path: str, module_name: str, error: BaseException):
        super().__init__("runTest")
        self._wallaby_file_path = str(Path(file_path).resolve())
        self._wallaby_module_name = module_name
        self._wallaby_test_name = f"[load error] {module_name}"
        self._wallaby_line_number = 0
        self._wallaby_error = error

    def runTest(self) -> None:
        raise self._wallaby_error


class _WallabyFileScopedSuite(unittest.TestSuite):
    def __init__(self, adapter: "InstrumentedUnittestAdapter", import_context: ModuleImportContext):
        super().__init__()
        self._adapter = adapter
        self._import_context = import_context

    def run(self, result, debug: bool = False):
        sys_path_state = self._adapter._prepend_sys_path(self._import_context.sys_path_entry)
        try:
            return super().run(result, debug)
        finally:
            self._adapter._restore_sys_path(sys_path_state)


class _WallabyUnittestResult(unittest.TestResult):
    def __init__(self, adapter: "InstrumentedUnittestAdapter"):
        super().__init__()
        self._adapter = adapter

    def startTest(self, test: unittest.case.TestCase) -> None:
        super().startTest(test)
        self._adapter.on_test_start(test)

    def stopTest(self, test: unittest.case.TestCase) -> None:
        self._adapter.on_test_stop(test)
        super().stopTest(test)

    def addError(self, test: unittest.case.TestCase, err: tuple[type[BaseException], BaseException, Any]) -> None:
        super().addError(test, err)
        self._adapter.on_test_outcome(test, TestResult.ERROR, err)

    def addFailure(self, test: unittest.case.TestCase, err: tuple[type[BaseException], BaseException, Any]) -> None:
        super().addFailure(test, err)
        self._adapter.on_test_outcome(test, TestResult.FAILED, err)

    def addSkip(self, test: unittest.case.TestCase, reason: str) -> None:
        super().addSkip(test, reason)
        self._adapter.on_test_skip(test, reason)

    def addExpectedFailure(
        self,
        test: unittest.case.TestCase,
        err: tuple[type[BaseException], BaseException, Any],
    ) -> None:
        super().addExpectedFailure(test, err)
        self._adapter.on_test_outcome(test, TestResult.XFAILED, err)

    def addUnexpectedSuccess(self, test: unittest.case.TestCase) -> None:
        super().addUnexpectedSuccess(test)
        self._adapter.on_test_outcome(test, TestResult.XPASSED, None)


class InstrumentedUnittestAdapter:
    """
    Runs unittest suites while keeping instrumentation and event semantics
    aligned with the pytest adapter.
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
        log: Optional[Callable[[str], None]] = None,
    ):
        self._log = log or (lambda msg: None)
        self._project_root = Path(project_root).resolve()
        self._on_test_call_start = on_test_call_start

        hints = hints or {}
        self.config = InstrumentationConfig(
            project_root=project_root,
            enable_coverage=enable_coverage,
            enable_value_logging=enable_value_logging,
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

        self._current_file: Optional[str] = None
        self._file_data: dict[str, TestFileData] = {}
        self._test_data: dict[int, TestItemData] = {}
        self._hints = hints
        self._selected_tests = selected_tests

    @property
    def events(self) -> EventEmitter:
        return self.session.events

    @property
    def coverage(self):
        return self.session.coverage

    @property
    def test_data(self) -> dict[int, TestItemData]:
        return self._test_data

    def get_source_map(self, path: str) -> Optional[SourceMap]:
        return self.session.get_source_map(path)

    def run(self, test_paths: list[str]) -> int:
        suite = self._build_suite(test_paths)

        collected = list(self._iter_tests(suite))
        test_infos: list[TestInfo] = []
        for test in collected:
            file_path = self._get_test_file_path(test)
            test_infos.append(
                TestInfo(
                    test_id=self._build_test_id(test, file_path),
                    test_name=self._get_test_name(test),
                    file_path=file_path,
                    line_number=self._get_test_line(test),
                )
            )
        self.events.emit(TestsCollectedEvent(tests=test_infos))

        result = _WallabyUnittestResult(self)
        suite.run(result)
        self._finalize_current_file()
        return 0 if result.wasSuccessful() else 1

    def _build_suite(self, test_paths: list[str]) -> unittest.TestSuite:
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()

        for raw_path in test_paths:
            candidate = Path(raw_path).resolve()
            if candidate.is_dir():
                for file_path in sorted(candidate.rglob("test*.py")):
                    if file_path.is_file():
                        filtered_suite = self._filter_selected_tests_from_suite(self._load_tests_from_file(file_path, loader))
                        if filtered_suite.countTestCases():
                            suite.addTests(filtered_suite)
                continue

            filtered_suite = self._filter_selected_tests_from_suite(self._load_tests_from_file(candidate, loader))
            if filtered_suite.countTestCases():
                suite.addTests(filtered_suite)

        return suite

    def _filter_selected_tests_from_suite(self, suite: unittest.TestSuite) -> unittest.TestSuite:
        if not isinstance(self._selected_tests, dict) or not self._selected_tests:
            return suite

        if isinstance(suite, _WallabyFileScopedSuite):
            filtered_suite = _WallabyFileScopedSuite(self, suite._import_context)
        else:
            filtered_suite = unittest.TestSuite()

        for test in suite:
            if isinstance(test, unittest.TestSuite):
                filtered_nested_suite = self._filter_selected_tests_from_suite(test)
                if filtered_nested_suite.countTestCases():
                    filtered_suite.addTest(filtered_nested_suite)
                continue

            if self._should_run_test(test):
                filtered_suite.addTest(test)

        return filtered_suite

    def _prepend_sys_path(self, path: str | Path) -> tuple[str, Optional[int]]:
        normalized = str(Path(path).resolve())
        original_index = None
        if normalized in sys.path:
            original_index = sys.path.index(normalized)
            sys.path.pop(original_index)
        sys.path.insert(0, normalized)
        return normalized, original_index

    def _restore_sys_path(self, state: tuple[str, Optional[int]]) -> None:
        normalized, original_index = state
        if normalized in sys.path:
            sys.path.remove(normalized)
        if original_index is not None:
            sys.path.insert(min(original_index, len(sys.path)), normalized)

    def _module_name_for_path(self, file_path: Path) -> str:
        import_context = resolve_module_import_context(file_path, self._project_root)
        if import_context.module_name:
            return import_context.module_name

        digest = hashlib.md5(str(file_path.resolve()).encode("utf-8")).hexdigest()[:12]
        return f"_wallaby_unittest_{digest}"

    def _load_tests_from_file(self, file_path: Path, loader: unittest.TestLoader) -> unittest.TestSuite:
        import_context = resolve_module_import_context(file_path, self._project_root)
        suite = _WallabyFileScopedSuite(self, import_context)
        module_name = import_context.module_name or self._module_name_for_path(file_path)
        normalized_path = str(file_path.resolve())

        sys.modules.pop(module_name, None)

        module = types.ModuleType(module_name)
        module.__file__ = normalized_path
        module.__name__ = module_name
        module.__package__ = import_context.package_name
        module.__loader__ = None
        module.__spec__ = importlib.util.spec_from_file_location(module_name, normalized_path)

        interceptor = self.session.interceptor
        if not interceptor:
            return suite

        sys_path_state = self._prepend_sys_path(import_context.sys_path_entry)
        try:
            content = interceptor.get_content(normalized_path)
            if interceptor.on_file_loaded:
                interceptor.on_file_loaded(normalized_path)
            _, _, code = interceptor.transform_and_cache(normalized_path, content)
            sys.modules[module_name] = module
            exec(code, module.__dict__)
            suite.addTests(loader.loadTestsFromModule(module))
            suite.addTests(self._collect_top_level_function_tests(module))
        except Exception:
            load_error = ImportError(
                f"Failed to import test module: {module_name}\n{traceback.format_exc()}"
            )
            suite.addTest(_WallabyLoadErrorTestCase(normalized_path, module_name, load_error))
        finally:
            self._restore_sys_path(sys_path_state)
            sys.modules.pop(module_name, None)

        return suite

    def _collect_top_level_function_tests(self, module: types.ModuleType) -> unittest.TestSuite:
        suite = unittest.TestSuite()

        if hasattr(module, "load_tests"):
            return suite

        for name, obj in vars(module).items():
            if not name.startswith("test_"):
                continue
            if not callable(obj):
                continue
            if inspect.isclass(obj):
                continue

            description = getattr(obj, "__wallaby_name__", None)
            suite.addTest(unittest.FunctionTestCase(obj, description=description))

        return suite

    def _iter_tests(self, suite: unittest.TestSuite):
        for test in suite:
            if isinstance(test, unittest.TestSuite):
                yield from self._iter_tests(test)
            else:
                yield test

    def _resolve_relative(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self._project_root)).replace("\\", "/")
        except ValueError:
            return str(path.resolve()).replace("\\", "/")

    def _get_function_for_test(self, test: unittest.case.TestCase):
        func = getattr(test, "_testFunc", None)
        if callable(func):
            return func

        method_name = getattr(test, "_testMethodName", None)
        if method_name and hasattr(test, method_name):
            method = getattr(test, method_name)
            if callable(method):
                return getattr(method, "__func__", method)

        return None

    def _get_test_file_path(self, test: unittest.case.TestCase) -> str:
        explicit_file = getattr(test, "_wallaby_file_path", None)
        if explicit_file:
            return str(Path(explicit_file).resolve())

        func = self._get_function_for_test(test)
        if func:
            # Unwrap decorated functions (e.g. @override_settings, @mock.patch)
            # that set __wrapped__ via functools.wraps. This ensures we get
            # the source file of the original test method, not the decorator.
            try:
                unwrapped = inspect.unwrap(func)
            except (ValueError, TypeError):
                unwrapped = func
            try:
                source_file = inspect.getsourcefile(unwrapped)
            except TypeError:
                source_file = None
            if source_file:
                return str(Path(source_file).resolve())

        module_name = getattr(test, "__module__", None)
        if module_name:
            module = sys.modules.get(module_name)
            module_file = getattr(module, "__file__", None) if module else None
            if module_file:
                return str(Path(module_file).resolve())

        test_id = test.id()
        module_part = test_id.rsplit(".", 2)[0] if "." in test_id else test_id
        module = sys.modules.get(module_part)
        module_file = getattr(module, "__file__", None) if module else None
        if module_file:
            return str(Path(module_file).resolve())

        return str(self._project_root)

    def _get_test_name(self, test: unittest.case.TestCase) -> str:
        explicit_name = getattr(test, "_wallaby_test_name", None)
        if explicit_name:
            return explicit_name

        func = self._get_function_for_test(test)
        if func:
            custom_name = getattr(func, "__wallaby_name__", None)
            if custom_name:
                return custom_name
            function_name = getattr(func, "__name__", None)
            if function_name:
                return function_name

        method_name = getattr(test, "_testMethodName", None)
        if method_name:
            return method_name

        return str(test)

    def _selected_test_path(self, test: unittest.case.TestCase) -> list[str]:
        test_name = self._get_test_name(test)

        if isinstance(test, unittest.FunctionTestCase):
            return [test_name]

        class_name = test.__class__.__name__
        if class_name and class_name != 'FunctionTestCase':
            return [class_name, test_name]

        return [test_name]

    def _should_run_test(self, test: unittest.case.TestCase) -> bool:
        if not isinstance(self._selected_tests, dict) or not self._selected_tests:
            return True

        return _spec_filter(self._selected_tests, self._selected_test_path(test))

    def _get_test_line(self, test: unittest.case.TestCase) -> int:
        explicit_line_number = getattr(test, "_wallaby_line_number", None)
        if explicit_line_number is not None:
            return int(explicit_line_number)

        func = self._get_function_for_test(test)
        if func and hasattr(func, "__code__"):
            return int(func.__code__.co_firstlineno)
        return 0

    def _build_test_id(self, test: unittest.case.TestCase, file_path: str) -> str:
        relative_file = self._resolve_relative(Path(file_path))
        func = self._get_function_for_test(test)
        method_name = getattr(test, "_testMethodName", None)

        if isinstance(test, unittest.FunctionTestCase):
            function_name = getattr(func, "__name__", "runTest")
            return f"{relative_file}::{function_name}"

        class_name = test.__class__.__name__
        if method_name:
            return f"{relative_file}::{class_name}::{method_name}"
        return f"{relative_file}::{class_name}"

    def _translate_traceback(self, tb_text: str) -> str:
        lines = tb_text.splitlines()
        translated: list[str] = []

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
                    line_number = int(line[line_start:line_end].strip())

                    source_map = self.get_source_map(path)
                    if source_map:
                        original_line = source_map.translate_traceback_line(line_number)
                        if original_line != line_number:
                            line = line[:line_start] + str(original_line) + line[line_end:]
                except (ValueError, IndexError):
                    pass
            translated.append(line)

        return "\n".join(translated)

    def on_test_start(self, test: unittest.case.TestCase) -> None:
        file_path = self._get_test_file_path(test)
        test_id = self._build_test_id(test, file_path)
        test_name = self._get_test_name(test)
        line_number = self._get_test_line(test)
        key = id(test)

        if self._current_file != file_path:
            self._finalize_current_file()
            self._current_file = file_path
            self._file_data[file_path] = TestFileData(path=file_path, start_time=time.perf_counter())
            self.events.emit(TestFileStartEvent(path=file_path, test_count=0))

        self._test_data[key] = TestItemData(
            test_id=test_id,
            test_name=test_name,
            file_path=file_path,
            line_number=line_number,
            start_time=time.perf_counter(),
            pre_test_coverage=self.session.get_coverage_snapshot(),
            pre_test_log_count=len(self.session.value_logs),
        )

        self.events.emit(
            TestStartEvent(
                test_id=test_id,
                test_name=test_name,
                file_path=file_path,
                line_number=line_number,
            )
        )

        if self._on_test_call_start:
            self._on_test_call_start(test_id)

    def on_test_outcome(
        self,
        test: unittest.case.TestCase,
        result: TestResult,
        err: Optional[tuple[type[BaseException], BaseException, Any]],
    ) -> None:
        data = self._test_data.get(id(test))
        if not data:
            return

        data.result = result
        if err:
            error_type, error_value, error_tb = err
            data.error_message = str(error_value)
            tb_text = "".join(traceback.format_exception(error_type, error_value, error_tb))
            data.error_traceback = self._translate_traceback(tb_text)

    def on_test_skip(self, test: unittest.case.TestCase, reason: str) -> None:
        data = self._test_data.get(id(test))
        if not data:
            return
        data.result = TestResult.SKIPPED
        data.error_message = reason

    def on_test_stop(self, test: unittest.case.TestCase) -> None:
        key = id(test)
        data = self._test_data.get(key)
        if not data:
            return

        data.duration_ms = (time.perf_counter() - data.start_time) * 1000

        lines_covered = 0
        if self.session.coverage:
            for file_path, ranges in self.session.coverage.executed_ranges.items():
                pre_ranges = data.pre_test_coverage.get(file_path, set())
                new_ranges = ranges - pre_ranges
                if new_ranges:
                    lines_covered += len(new_ranges)

        data.value_logs = self.session.value_logs[data.pre_test_log_count :]

        self.events.emit(
            TestEndEvent(
                test_id=data.test_id,
                test_name=data.test_name,
                file_path=data.file_path,
                result=data.result,
                duration_ms=data.duration_ms,
                error_message=data.error_message,
                error_traceback=data.error_traceback,
                lines_covered=lines_covered,
            )
        )

        file_data = self._file_data.get(data.file_path)
        if file_data:
            if data.result == TestResult.PASSED:
                file_data.passed_count += 1
            elif data.result == TestResult.SKIPPED or data.result == TestResult.XFAILED:
                file_data.skipped_count += 1
            elif data.result == TestResult.ERROR:
                file_data.error_count += 1
            else:
                file_data.failed_count += 1

        del self._test_data[key]

    def _finalize_current_file(self) -> None:
        if not self._current_file:
            return

        file_data = self._file_data.get(self._current_file)
        if not file_data:
            self._current_file = None
            return

        file_data.duration_ms = (time.perf_counter() - file_data.start_time) * 1000
        self.events.emit(
            TestFileEndEvent(
                path=file_data.path,
                passed_count=file_data.passed_count,
                failed_count=file_data.failed_count,
                skipped_count=file_data.skipped_count,
                error_count=file_data.error_count,
                duration_ms=file_data.duration_ms,
            )
        )
        self._current_file = None


from .django_unittest_support import patch_unittest_adapter as _patch_django

_patch_django(sys.modules[__name__])
