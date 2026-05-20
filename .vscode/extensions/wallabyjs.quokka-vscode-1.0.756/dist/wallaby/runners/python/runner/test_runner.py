from __future__ import annotations

"""Custom test runner with instrumentation support."""

import sys
import os
import traceback
import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable, Any
from enum import Enum

from .transformer import CodeTransformer
from .file_interceptor import FileInterceptor
from .runtime_globals import RuntimeGlobals, CoverageData, TimeLog, ValueLog
from .source_map import SourceMap


class TestStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class TestResult:
    """Result of a single test."""
    
    name: str
    status: TestStatus
    duration: float = 0.0
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None
    # Original line numbers in traceback (after source map translation)
    error_lines: list[tuple[str, int]] = field(default_factory=list)
    # Coverage data specific to this test
    covered_lines: dict[str, set[int]] = field(default_factory=dict)
    # Values logged during this test
    value_logs: list[ValueLog] = field(default_factory=list)


@dataclass
class TestRunResult:
    """Result of a complete test run."""
    
    tests: list[TestResult] = field(default_factory=list)
    total_duration: float = 0.0
    coverage: Optional[CoverageData] = None
    
    @property
    def passed(self) -> int:
        return sum(1 for t in self.tests if t.status == TestStatus.PASSED)
    
    @property
    def failed(self) -> int:
        return sum(1 for t in self.tests if t.status == TestStatus.FAILED)
    
    @property
    def errors(self) -> int:
        return sum(1 for t in self.tests if t.status == TestStatus.ERROR)
    
    @property
    def skipped(self) -> int:
        return sum(1 for t in self.tests if t.status == TestStatus.SKIPPED)
    
    @property
    def total(self) -> int:
        return len(self.tests)


@dataclass
class TestRunner:
    """
    Custom test runner with code instrumentation.
    
    Features:
    - Intercepts file reads to use cached content
    - Transforms code for coverage and value logging
    - Provides source maps for error translation
    - Injects runtime globals for instrumented code
    """
    
    project_root: str
    enable_coverage: bool = True
    enable_value_logging: bool = True
    
    # Components
    transformer: CodeTransformer = field(default_factory=CodeTransformer)
    interceptor: FileInterceptor = field(default_factory=FileInterceptor)
    runtime: RuntimeGlobals = field(default_factory=RuntimeGlobals)
    
    # Callbacks
    on_test_start: Optional[Callable[[str], None]] = None
    on_test_complete: Optional[Callable[[TestResult], None]] = None
    on_coverage_hit: Optional[Callable[[str, int], None]] = None
    on_value_logged: Optional[Callable[[ValueLog], None]] = None
    on_time_logged: Optional[Callable[[TimeLog], None]] = None
    
    def __post_init__(self):
        # Configure transformer
        self.transformer.enable_coverage = self.enable_coverage
        self.transformer.enable_value_logging = self.enable_value_logging
        
        # Link interceptor to transformer
        self.interceptor.transformer = self.transformer
        
        # Setup callback to register covered lines when files are transformed
        self.interceptor.on_file_transformed = self._on_file_transformed
        
        # Setup runtime callbacks
        self.runtime.on_coverage_hit = self.on_coverage_hit
        self.runtime.on_value_logged = self.on_value_logged
        self.runtime.on_time_logged = self.on_time_logged
    
    def _on_file_transformed(self, path: str, source_map: SourceMap) -> None:
        """Called when a file is transformed - registers coverage ranges."""
        if source_map.range_count > 0:
            self.runtime.coverage.total_ranges[path] = source_map.range_count
    
    def set_runtime_global(self, name: str, value: Any) -> None:
        """Set a global variable accessible to instrumented code."""
        self.runtime.set_global(name, value)
    
    def get_source_map(self, path: str) -> Optional[SourceMap]:
        """Get source map for a file."""
        return self.interceptor.get_source_map(path)
    
    def translate_traceback(self, tb_text: str) -> str:
        """Translate line numbers in a traceback to original source lines."""
        lines = tb_text.splitlines()
        translated_lines = []
        
        for line in lines:
            # Look for file/line patterns like 'File "path", line N'
            if 'File "' in line and '", line ' in line:
                try:
                    # Extract path and line number
                    start = line.index('File "') + 6
                    end = line.index('", line ')
                    path = line[start:end]
                    
                    line_start = end + 8
                    line_end = line.find(",", line_start)
                    if line_end == -1:
                        line_end = len(line)
                    line_num = int(line[line_start:line_end].strip())
                    
                    # Translate using source map
                    source_map = self.get_source_map(path)
                    if source_map:
                        original_line = source_map.translate_traceback_line(line_num)
                        if original_line != line_num:
                            line = line[:line_start] + str(original_line) + line[line_end:]
                except (ValueError, IndexError):
                    pass
            
            translated_lines.append(line)
        
        return "\n".join(translated_lines)
    
    def discover_tests(self, test_path: Optional[str] = None) -> list[str]:
        """Discover test files in the project."""
        if test_path is None:
            test_path = os.path.join(self.project_root, "tests")
        elif not os.path.isabs(test_path):
            # Make relative paths relative to project_root
            test_path = os.path.join(self.project_root, test_path)
        
        test_files = []
        test_path_obj = Path(test_path)
        
        if test_path_obj.is_file():
            test_files.append(str(test_path_obj))
        elif test_path_obj.is_dir():
            for path in test_path_obj.rglob("test_*.py"):
                test_files.append(str(path))
            for path in test_path_obj.rglob("*_test.py"):
                test_files.append(str(path))
        
        return test_files
    
    def run_tests(
        self,
        test_path: Optional[str] = None,
        test_filter: Optional[str] = None,
    ) -> TestRunResult:
        """
        Run tests with instrumentation.
        
        Args:
            test_path: Path to test file or directory (defaults to tests/)
            test_filter: Optional filter pattern for test names
        """
        import time
        
        result = TestRunResult()
        start_time = time.time()
        
        # Install hooks
        self.interceptor.install_import_hook([self.project_root])
        self.runtime.install()
        
        try:
            # Ensure project root is in path
            if self.project_root not in sys.path:
                sys.path.insert(0, self.project_root)
            
            # Discover tests
            test_files = self.discover_tests(test_path)
            
            for test_file in test_files:
                result.tests.extend(self._run_test_file(test_file, test_filter))
            
            # Store overall coverage
            result.coverage = self.runtime.coverage
            
        finally:
            result.total_duration = time.time() - start_time
            
            # Cleanup
            self.runtime.uninstall()
            self.interceptor.uninstall_import_hook()
        
        return result
    
    def _run_test_file(
        self,
        test_file: str,
        test_filter: Optional[str] = None,
    ) -> list[TestResult]:
        """Run all tests in a single file."""
        import time
        
        results = []
        
        # Load test module
        try:
            # Clear from cache to force reload with instrumentation
            module_name = self._path_to_module_name(test_file)
            if module_name in sys.modules:
                del sys.modules[module_name]
            
            # Get content
            content = self.interceptor.get_content(test_file)
            transformed, source_map, code = self.interceptor.transform_and_cache(test_file, content)
            
            # Execute in a fresh namespace
            namespace = {"__name__": module_name, "__file__": test_file}
            exec(code, namespace)
            
            # Find test functions and classes
            tests = self._collect_tests(namespace, test_filter)
            
            for test_name, test_callable in tests:
                if self.on_test_start:
                    self.on_test_start(test_name)
                
                # Reset per-test tracking
                pre_coverage = {f: ranges.copy() for f, ranges in self.runtime.coverage.executed_ranges.items()}
                pre_logs = len(self.runtime.value_logs)
                
                test_result = TestResult(name=test_name, status=TestStatus.PASSED)
                test_start = time.time()
                
                try:
                    test_callable()
                except AssertionError as e:
                    test_result.status = TestStatus.FAILED
                    test_result.error_message = str(e)
                    test_result.error_traceback = self.translate_traceback(
                        traceback.format_exc()
                    )
                except Exception as e:
                    test_result.status = TestStatus.ERROR
                    test_result.error_message = str(e)
                    test_result.error_traceback = self.translate_traceback(
                        traceback.format_exc()
                    )
                
                test_result.duration = time.time() - test_start
                
                # Capture test-specific coverage (ranges covered during this test)
                for file, ranges in self.runtime.coverage.executed_ranges.items():
                    pre_ranges = pre_coverage.get(file, set())
                    new_ranges = ranges - pre_ranges
                    if new_ranges:
                        test_result.covered_lines[file] = new_ranges
                
                # Capture test-specific value logs
                test_result.value_logs = self.runtime.value_logs[pre_logs:]
                
                results.append(test_result)
                
                if self.on_test_complete:
                    self.on_test_complete(test_result)
        
        except Exception as e:
            # Error loading/parsing test file
            results.append(TestResult(
                name=f"[{test_file}]",
                status=TestStatus.ERROR,
                error_message=f"Failed to load test file: {e}",
                error_traceback=self.translate_traceback(traceback.format_exc()),
            ))
        
        return results
    
    def _path_to_module_name(self, path: str) -> str:
        """Convert file path to module name."""
        rel_path = os.path.relpath(path, self.project_root)
        module_name = rel_path.replace(os.sep, ".").replace("/", ".")
        if module_name.endswith(".py"):
            module_name = module_name[:-3]
        return module_name
    
    def _collect_tests(
        self,
        namespace: dict[str, Any],
        test_filter: Optional[str] = None,
    ) -> list[tuple[str, Callable[[], None]]]:
        """Collect test functions and methods from a module namespace."""
        tests = []
        
        for name, obj in namespace.items():
            # Test functions
            if name.startswith("test_") and callable(obj):
                if test_filter is None or test_filter in name:
                    tests.append((name, obj))
            
            # Test classes
            elif isinstance(obj, type) and name.startswith("Test"):
                instance = obj()
                for method_name in dir(instance):
                    if method_name.startswith("test_"):
                        method = getattr(instance, method_name)
                        if callable(method):
                            full_name = f"{name}::{method_name}"
                            if test_filter is None or test_filter in full_name:
                                tests.append((full_name, method))
        
        return tests
    
    def format_results(self, result: TestRunResult) -> str:
        """Format test results for display."""
        lines = []
        lines.append("=" * 60)
        lines.append("TEST RESULTS")
        lines.append("=" * 60)
        
        for test in result.tests:
            status_symbol = {
                TestStatus.PASSED: "✓",
                TestStatus.FAILED: "✗",
                TestStatus.ERROR: "!",
                TestStatus.SKIPPED: "○",
            }[test.status]
            
            lines.append(f"{status_symbol} {test.name} ({test.duration:.3f}s)")
            
            if test.error_message:
                lines.append(f"  Error: {test.error_message}")
            if test.error_traceback:
                for tb_line in test.error_traceback.splitlines()[-5:]:
                    lines.append(f"    {tb_line}")
        
        lines.append("-" * 60)
        lines.append(
            f"Total: {result.total} | "
            f"Passed: {result.passed} | "
            f"Failed: {result.failed} | "
            f"Errors: {result.errors} | "
            f"Duration: {result.total_duration:.3f}s"
        )
        
        if result.coverage:
            lines.append(f"Coverage: {result.coverage.get_coverage_percent():.1f}%")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
