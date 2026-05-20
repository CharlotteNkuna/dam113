#!/usr/bin/env python3
from __future__ import annotations

"""
Python Test Worker - IPC Communication Module

This module handles IPC communication with the parent process using stdin/stdout.
Messages are JSON-formatted and wrapped with start/end markers.
"""

import sys
import os
import importlib
import importlib.util
import json
import traceback
import site
import tokenize
import fnmatch
import configparser
import hashlib
import inspect
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Any, Optional, List, Set

# Import the tracer
from tracer import Tracer, init_tracer, get_tracer, destroy_tracer

# Note: runner module imports are done lazily in _execute_tests() after sys.path is configured
# This allows test frameworks to be imported from the user's project environment

MESSAGE_START = '###wms###'
MESSAGE_END = '###wme###'

_DEFAULT_PYTEST_PYTHON_FILES = ['test_*.py', '*_test.py']


def _read_pytest_python_file_patterns(project_root: str) -> List[str]:
    config_paths = [
        ('pytest.ini', 'pytest', 'python_files'),
        ('tox.ini', 'pytest', 'python_files'),
        ('setup.cfg', 'tool:pytest', 'python_files'),
    ]

    for file_name, section, option in config_paths:
        config_path = os.path.join(project_root, file_name)
        if not os.path.exists(config_path):
            continue

        parser = configparser.ConfigParser()
        try:
            parser.read(config_path, encoding='utf-8')
        except Exception:
            continue

        if parser.has_option(section, option):
            raw_value = parser.get(section, option)
            patterns = [pattern for pattern in raw_value.split() if pattern]
            if patterns:
                return patterns

    pyproject_path = os.path.join(project_root, 'pyproject.toml')
    if os.path.exists(pyproject_path):
        try:
            import tomllib  # type: ignore[attr-defined]

            with open(pyproject_path, 'rb') as handle:
                data = tomllib.load(handle)

            raw_value = (((data.get('tool') or {}).get('pytest') or {}).get('ini_options') or {}).get('python_files')
            if isinstance(raw_value, str):
                patterns = [pattern for pattern in raw_value.split() if pattern]
                if patterns:
                    return patterns
            elif isinstance(raw_value, list):
                patterns = [str(pattern).strip() for pattern in raw_value if str(pattern).strip()]
                if patterns:
                    return patterns
        except Exception:
            pass

    return _DEFAULT_PYTEST_PYTHON_FILES.copy()


def _read_pytest_testpaths(project_root: str) -> List[str]:
    config_paths = [
        ('pytest.ini', 'pytest', 'testpaths'),
        ('tox.ini', 'pytest', 'testpaths'),
        ('setup.cfg', 'tool:pytest', 'testpaths'),
    ]

    for file_name, section, option in config_paths:
        config_path = os.path.join(project_root, file_name)
        if not os.path.exists(config_path):
            continue

        parser = configparser.ConfigParser()
        try:
            parser.read(config_path, encoding='utf-8')
        except Exception:
            continue

        if parser.has_option(section, option):
            raw_value = parser.get(section, option)
            paths = [path for path in raw_value.split() if path]
            if paths:
                return paths

    pyproject_path = os.path.join(project_root, 'pyproject.toml')
    if os.path.exists(pyproject_path):
        try:
            import tomllib  # type: ignore[attr-defined]

            with open(pyproject_path, 'rb') as handle:
                data = tomllib.load(handle)

            raw_value = (((data.get('tool') or {}).get('pytest') or {}).get('ini_options') or {}).get('testpaths')
            if isinstance(raw_value, str):
                paths = [path for path in raw_value.split() if path]
                if paths:
                    return paths
            elif isinstance(raw_value, list):
                paths = [str(path).strip() for path in raw_value if str(path).strip()]
                if paths:
                    return paths
        except Exception:
            pass

    return []


def _is_within_pytest_testpaths(test_path: str, project_root: str, testpaths: Optional[List[str]] = None) -> bool:
    configured_testpaths = testpaths if testpaths is not None else _read_pytest_testpaths(project_root)
    if not configured_testpaths:
        return True

    try:
        relative_path = os.path.relpath(test_path, project_root)
    except Exception:
        return False

    if relative_path.startswith('..'):
        return False

    normalized_path = relative_path.replace('\\', '/').lstrip('./')
    for configured_path in configured_testpaths:
        normalized_testpath = configured_path.replace('\\', '/').lstrip('./').rstrip('/')
        if not normalized_testpath:
            continue
        if normalized_path == normalized_testpath or normalized_path.startswith(normalized_testpath + '/'):
            return True

    return False


def _is_pytest_collectable_path(
    test_path: str,
    project_root: str,
    python_file_patterns: Optional[List[str]] = None,
    testpaths: Optional[List[str]] = None,
) -> bool:
    if not _is_within_pytest_testpaths(test_path, project_root, testpaths):
        return False

    if os.path.isdir(test_path):
        return True

    if not test_path.endswith('.py'):
        return True

    patterns = python_file_patterns or _read_pytest_python_file_patterns(project_root)
    file_name = os.path.basename(test_path)
    return any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns)


def _filter_pytest_test_paths(test_paths: List[str], project_root: str) -> List[str]:
    patterns = _read_pytest_python_file_patterns(project_root)
    testpaths = _read_pytest_testpaths(project_root)
    return [
        test_path
        for test_path in test_paths
        if _is_pytest_collectable_path(test_path, project_root, patterns, testpaths)
    ]


def _should_report_exec_error(
    path: str,
    error: Exception,
    project_root: str,
    framework_name: str,
    current_test_id: Optional[str] = None,
) -> bool:
    if isinstance(error, SyntaxError):
        return False
    if not path:
        return False
    if project_root and not path.startswith(project_root):
        return False
    if framework_name == 'pytest' and current_test_id:
        return False
    return True


def _project_error_origin_path(error: Exception, project_root: str) -> Optional[str]:
    traceback_obj = getattr(error, '__traceback__', None)
    if traceback_obj is None:
        return None

    for frame in reversed(traceback.extract_tb(traceback_obj)):
        frame_path = getattr(frame, 'filename', None)
        if not frame_path:
            continue
        normalized = str(Path(frame_path).resolve())
        if project_root and normalized.startswith(project_root):
            return normalized

    return None


def _error_origin_matches_path(path: str, error: Exception, project_root: str) -> bool:
    origin_path = _project_error_origin_path(error, project_root)
    if not origin_path:
        return True
    return origin_path == str(Path(path).resolve())


class WallabyContentProvider:
    """
    Content provider that supplies file content from Wallaby's cache.
    
    This provider attempts to read file content from the Wallaby cache
    directory, falling back to None if the file isn't in cache.
    """
    
    def __init__(
        self,
        files_cache: Dict[str, Dict[str, Any]],
        originalCacheRoot: str,
        file_metadata_by_path: Optional[Dict[str, Dict[str, Any]]] = None,
        project_root: Optional[str] = None,
        log_func: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize the content provider.
        
        Args:
            file_metadata: Dict mapping normalized absolute paths to file info
                          containing 'path' (relative path for cache lookup)
            cache_root: Root of Wallaby cache directory
            log_func: Optional logging function
        """
        self._files_cache = files_cache
        self._originalCacheRoot = originalCacheRoot
        self._file_metadata_by_path = file_metadata_by_path or {}
        self._log = log_func or (lambda msg: None)
        self._project_root = project_root or ''
    
    def get_cached_content(self, path: str) -> Optional[str]:
        """
        Get cached content for a file path if available.
        
        Args:
            path: The normalized absolute path to the file
            
        Returns:
            The cached content if available, None otherwise
        """
        # Convert absolute path to relative path for cache lookup
        if self._project_root and path.startswith(self._project_root):
            relative_path = path[len(self._project_root):].lstrip(os.sep)
        else:
            relative_path = path

        file_info = self._files_cache.get(relative_path)
        cache_rel_path = None
        if file_info is not None:
            if file_info.get('inOriginalFilesCache', False):
                cache_rel_path = relative_path
        else:
            normalized_path = str(Path(path).resolve())
            metadata = self._file_metadata_by_path.get(normalized_path)
            if metadata and metadata.get('inOriginalFilesCache', False) and metadata.get('path'):
                cache_rel_path = metadata['path']

        if not cache_rel_path:
            return None

        cache_path = os.path.join(self._originalCacheRoot, cache_rel_path)
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return content
        except FileNotFoundError:
            return None
        except Exception:
            return None

# Duplicate stdout/stderr file descriptors at the OS level before anything can redirect them.
# Using os.dup() creates new file descriptors that won't be affected by pytest's fd-level
# capture (which redirects fd 1 and 2). We then wrap these in new file objects for IPC.
_ORIGINAL_STDOUT_FD = os.dup(sys.stdout.fileno())
_ORIGINAL_STDERR_FD = os.dup(sys.stderr.fileno())
_ORIGINAL_STDOUT = os.fdopen(_ORIGINAL_STDOUT_FD, 'w', encoding='utf-8', closefd=False)
_ORIGINAL_STDERR = os.fdopen(_ORIGINAL_STDERR_FD, 'w', encoding='utf-8', closefd=False)

# Set to a file path to enable logging, or None to disable
# LOG_FILE: Optional[str] = None
LOG_FILE: Optional[str] = (
    os.environ.get('WALLABY_PYTHON_LOG_FILE')
    or ('/tmp/wallaby-python-worker.log' if os.environ.get('WALLABY_INTEGRATION_TEST_RUN') else None)
)

def log(message: str) -> None:
    """
    Append a log message to the log file if logging is enabled.
    
    Args:
        message: The message to log
    """
    if LOG_FILE is None:
        return
    try:
        timestamp = datetime.now().isoformat()
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f'[{timestamp}] {message}\n')
    except Exception:
        pass  # Silently ignore logging errors


def log_python_environment() -> None:
    """
    Log information about the current Python environment.
    This is useful for debugging venv detection issues.
    """
    log(f'Python executable: {sys.executable}')
    log(f'Python version: {sys.version}')
    log(f'Python prefix: {sys.prefix}')
    log(f'Python base_prefix: {sys.base_prefix}')
    
    # Check if we're in a virtual environment
    in_venv = sys.prefix != sys.base_prefix
    log(f'In virtual environment: {in_venv}')
    
    if 'VIRTUAL_ENV' in os.environ:
        log(f'VIRTUAL_ENV env var: {os.environ["VIRTUAL_ENV"]}')


def clear_project_modules(project_root: str) -> None:
    """
    Remove project modules from sys.modules so source changes are reloaded.
    This ensures re-runs pick up updated code rather than cached imports.
    """
    try:
        project_root_path = Path(project_root).resolve()
    except Exception:
        project_root_path = Path(project_root)

    removed = []
    skip_fragments = (f"{os.sep}.venv{os.sep}", f"{os.sep}venv{os.sep}", f"{os.sep}site-packages{os.sep}")
    for name, module in list(sys.modules.items()):
        module_file = getattr(module, '__file__', None)
        if not module_file:
            module_spec = getattr(module, '__spec__', None)
            module_file = getattr(module_spec, 'origin', None) if module_spec else None
        if not module_file:
            continue
        if module_file in ('built-in', 'frozen') or module_file.startswith('<'):
            continue
        try:
            module_path = Path(module_file).resolve()
        except Exception:
            continue
        module_path_str = str(module_path)
        if any(fragment in module_path_str for fragment in skip_fragments):
            continue
        try:
            if module_path.is_relative_to(project_root_path):
                removed.append(name)
        except Exception:
            if module_path_str.startswith(str(project_root_path)):
                removed.append(name)

    for name in removed:
        sys.modules.pop(name, None)

    importlib.invalidate_caches()



def configure_virtual_environment(project_root: str) -> bool:
    """
    Detect and configure the virtual environment for the project.
    
    NOTE: This is now a fallback mechanism. The preferred approach is for the
    Node.js side to detect the venv and spawn the venv's Python directly.
    When the venv's Python is used, this function is not needed.
    
    This adds the virtual environment's site-packages to sys.path so that
    packages installed in the venv (like pytest) can be imported.
    
    Searches the project root and walks up parent directories to find a venv.
    
    Args:
        project_root: The root directory of the project
        
    Returns:
        True if a virtual environment was found and configured, False otherwise
    """
    # If we're already running from a venv Python, no need to configure
    if sys.prefix != sys.base_prefix:
        log(f'Already running in virtual environment: {sys.prefix}')
        return True
    
    # Common virtual environment directory names
    venv_names = ['.venv', 'venv', '.env', 'env', '.virtualenv', 'virtualenv']
    
    # Start from project root and walk up to parent directories
    current_path = Path(project_root).resolve()
    
    # Limit how far up we walk (e.g., don't go past home directory or root)
    max_depth = 10
    depth = 0
    
    while current_path != current_path.parent and depth < max_depth:
        log(f'Searching for venv in: {current_path}')
        
        for venv_name in venv_names:
            venv_path = current_path / venv_name
            if venv_path.is_dir():
                # Determine the site-packages path based on OS
                if sys.platform == 'win32':
                    site_packages = venv_path / 'Lib' / 'site-packages'
                    scripts_dir = venv_path / 'Scripts'
                else:
                    # macOS / Linux
                    python_version = f'python{sys.version_info.major}.{sys.version_info.minor}'
                    site_packages = venv_path / 'lib' / python_version / 'site-packages'
                    scripts_dir = venv_path / 'bin'
                
                if site_packages.is_dir():
                    # Add site-packages to sys.path
                    site_packages_str = str(site_packages)
                    if site_packages_str not in sys.path:
                        sys.path.insert(0, site_packages_str)
                        log(f'Added venv site-packages to path: {site_packages_str}')
                    
                    # Also add scripts/bin directory for entry points
                    scripts_str = str(scripts_dir)
                    if scripts_str not in sys.path:
                        sys.path.insert(0, scripts_str)
                    
                    # Update PATH environment variable
                    os.environ['PATH'] = scripts_str + os.pathsep + os.environ.get('PATH', '')
                    
                    # Set VIRTUAL_ENV environment variable
                    os.environ['VIRTUAL_ENV'] = str(venv_path)
                    
                    log(f'Configured virtual environment: {venv_path}')
                    return True
                else:
                    log(f'Found venv directory but no site-packages: {venv_path}')
        
        # Move up to parent directory
        current_path = current_path.parent
        depth += 1
    
    log(f'No virtual environment found starting from {project_root}')
    return False

class TestWorker:
    """
    Handles IPC communication with the parent process.
    
    Communication protocol:
    - Incoming messages: Read from stdin, buffered until complete message is received
    - Outgoing messages: Written to stdout wrapped in MESSAGE_START/MESSAGE_END markers
    - Error messages: Written to stderr wrapped in MESSAGE_START/MESSAGE_END markers
    - Message format: JSON with 'type' and 'data' fields
    """
    
    def __init__(
        self,
        worker_id: str,
        originalCacheRoot: str,
        log_limits: Optional[Dict[str, Any]] = None,
        framework_version: Optional[str] = None,
    ):
        self._id = int(worker_id)
        self._originalCacheRoot = originalCacheRoot
        self._framework_version = (framework_version or "pytest@1.0.0").split(",")[0]
        self._buffer = ''
        self._handlers: Dict[str, Callable[[Any], None]] = {}
        self._tracer: Optional[Tracer] = None
        self._session_id: Optional[str] = None
        self._config: Optional[Dict[str, Any]] = None
        self._log_limits = log_limits
        
        # Persistent file cache across runs (files are sent incrementally)
        # Maps file ID -> file info dict
        self._files_cache: Dict[int, Dict[str, Any]] = {}
        
        # Per-run mappings (rebuilt each run from cache)
        self._file_path_to_id: Dict[str, int] = {}
        self._test_file_ids: Set[int] = set()
        self._file_metadata: Dict[str, Dict[str, Any]] = {}  # path -> file info for content provider
        self._project_root: Optional[str] = None
        self._log_markers_by_path: Dict[str, list[dict[str, Any]]] = {}
        self._reported_global_errors: Set[str] = set()
        self._execution_stage = 'idle'
        self._current_test_paths: List[str] = []
        self._hook_modules: Dict[str, Any] = {}
        self._active_initializer: Optional[str] = None
        self._initializer_ran = False
        self._initializer_teardown: Optional[Callable[[], Any]] = None
        
        log(f'TestWorker initialized with id={self._id}')
        
        # Register built-in message handlers
        self._register_handlers()
        
        # Initialize the tracer with our send function
        self._tracer = init_tracer(self.send)
        if self._tracer:
            self._tracer.set_log_limits(log_limits)
    
    def _register_handlers(self) -> None:
        """Register message type handlers."""
        self._handlers['in:connected'] = self._on_connected
        self._handlers['in:ping'] = self._on_ping
        self._handlers['in:run'] = self._on_run
        self._handlers['in:stop'] = self._on_stop
        self._handlers['in:teardown'] = self._on_teardown
        self._handlers['in:tracer.resume'] = self._on_tracer_resume

    # -------------------------------------------------------------------------
    # Output Methods
    # -------------------------------------------------------------------------
    
    def send(self, message: Dict[str, Any]) -> None:
        """
        Send a message to the parent process via stdout.
        
        Args:
            message: Dictionary to be JSON-encoded and sent
        """
        log(f'Sending message: {message}')
        self._report_via_stdout(json.dumps(message))
    
    def _report_via_stdout(self, payload: str) -> None:
        """
        Write a payload to stdout with message markers.
        
        Uses the original stdout captured at module load time to ensure
        IPC communication works even when sys.stdout is redirected.
        
        Args:
            payload: String payload to send
        """
        if not payload:
            return
        _ORIGINAL_STDOUT.write(f'{MESSAGE_START}{payload}{MESSAGE_END}')
        _ORIGINAL_STDOUT.flush()
    
    def _report_via_stderr(self, error: Any) -> None:
        """
        Write an error to stderr with message markers.
        
        Uses the original stderr captured at module load time to ensure
        IPC communication works even when sys.stderr is redirected.
        
        Args:
            error: Error object or string to send
        """
        if error is None:
            error_str = ''
        elif isinstance(error, Exception):
            error_str = f'{type(error).__name__}: {str(error)}'
        elif isinstance(error, str):
            error_str = error
        else:
            error_str = str(error)
        
        _ORIGINAL_STDERR.write(f'{MESSAGE_START}{error_str}{MESSAGE_END}')
        _ORIGINAL_STDERR.flush()
    
    def report_error(self, error: Any) -> None:
        """
        Report an error to the parent process.
        
        Args:
            error: Error object or string to report
        """
        log(f'Reporting error: {error}')
        self._report_via_stderr(error)
    
    def emit_diagnostic(self, diagnostic: Dict[str, Any]) -> None:
        """
        Emit a diagnostic message to the parent process.
        
        Args:
            diagnostic: Diagnostic information dictionary
        """
        diagnostic['_diagnostic'] = 1
        diagnostic['_p'] = '###wpm###'
        self._report_via_stdout(json.dumps(diagnostic))

    def _set_execution_stage(self, stage: str) -> None:
        self._execution_stage = stage
        log(f'Execution stage: {stage}')

    def _resolve_hook_path(self, hook_target: str, project_root: str) -> Optional[Path]:
        candidate = Path(hook_target.strip())
        if not candidate.is_absolute():
            candidate = Path(project_root) / candidate

        try:
            resolved = candidate.resolve()
        except Exception:
            return None

        return resolved if resolved.is_file() else None

    def _load_hook_module(self, hook_path: Path) -> Any:
        cache_key = str(hook_path)
        cached = self._hook_modules.get(cache_key)
        if cached is not None:
            return cached

        digest = hashlib.md5(cache_key.encode('utf-8')).hexdigest()[:12]
        module_name = f'_wallaby_python_hook_{digest}'
        spec = importlib.util.spec_from_file_location(module_name, str(hook_path))
        if spec is None or spec.loader is None:
            raise ImportError(f'Unable to load hook module from {hook_path}')

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        self._hook_modules[cache_key] = module
        return module

    def _call_hook(self, hook: Any, context: Dict[str, Any]) -> Any:
        try:
            signature = inspect.signature(hook)
            if len(signature.parameters) == 0:
                return hook()
        except (TypeError, ValueError):
            pass
        return hook(context)

    def _invoke_hook(self, hook_target: str, hook_name: str, config: Dict[str, Any]) -> Any:
        project_root = config.get('localProjectDir', os.getcwd())
        hook_path = self._resolve_hook_path(hook_target, project_root)
        if hook_path is None:
            log(f'Ignoring {hook_name} hook target (not a file path): {hook_target}')
            return None

        module = self._load_hook_module(hook_path)
        hook = getattr(module, hook_name, None)
        if not callable(hook):
            return None

        context = {
            'config': config,
            'projectRoot': project_root,
            'workerId': self._id,
            'log': log,
        }
        return self._call_hook(hook, context)

    def _run_initializer_if_needed(self, config: Dict[str, Any]) -> bool:
        initializer = config.get('initializer')
        if not isinstance(initializer, str) or not initializer.strip():
            self._active_initializer = None
            self._initializer_ran = False
            self._initializer_teardown = None
            return True

        initializer = initializer.strip()
        if self._active_initializer != initializer:
            self._active_initializer = initializer
            self._initializer_ran = False
            self._initializer_teardown = None

        if self._initializer_ran:
            return True

        try:
            result = self._invoke_hook(initializer, 'setup', config)
            if callable(result):
                self._initializer_teardown = result
            self._initializer_ran = True
            return True
        except Exception as error:
            self._emit_runtime_error_diagnostic(
                'Python worker setup hook failed.',
                error,
                config,
                extra={'setupHook': initializer},
            )
            if self._tracer:
                self._tracer.report_global_error(error)
                self._tracer.started({})
                self._tracer.complete({})
            return False

    def _truncate_diagnostic_value(self, value: Any, limit: int = 2000) -> str:
        if value is None:
            return ''
        try:
            text = value if isinstance(value, str) else json.dumps(value, default=str, sort_keys=True)
        except Exception:
            text = str(value)
        if len(text) <= limit:
            return text
        return f'{text[:limit]}... [truncated {len(text) - limit} chars]'

    def _summarize_test_files(self, config: Dict[str, Any], limit: int = 10) -> List[str]:
        summary: List[str] = []
        for test_file in config.get('testFiles', [])[:limit]:
            path_value = (
                test_file.get('normalizedRelativePath')
                or test_file.get('path')
                or test_file.get('file')
                or ''
            )
            if path_value:
                summary.append(path_value)
        return summary

    def _build_run_context(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        config = config or {}
        return {
            'workerId': self._id,
            'stage': self._execution_stage,
            'frameworkVersion': self._framework_version,
            'projectRoot': config.get('localProjectDir') or self._project_root or '',
            'cwd': os.getcwd(),
            'pythonExecutable': sys.executable,
            'pythonVersion': sys.version.splitlines()[0],
            'pythonPrefix': sys.prefix,
            'pythonBasePrefix': sys.base_prefix,
            'virtualEnv': os.environ.get('VIRTUAL_ENV', ''),
            'testFileCount': len(config.get('testFiles', [])),
            'testFiles': self._summarize_test_files(config),
            'resolvedTestPaths': self._current_test_paths[:10],
            'deletedFilesCount': len(config.get('deletedFiles', [])),
            'hasTraceContext': bool(config.get('traceContext')),
        }

    def _emit_runtime_error_diagnostic(
        self,
        message: str,
        error: Exception,
        config: Optional[Dict[str, Any]] = None,
        *,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        context = self._build_run_context(config)
        if extra:
            context.update(extra)

        diagnostic_lines = [
            message,
            f'Error: {type(error).__name__}: {error}',
            f'Context: {self._truncate_diagnostic_value(context, 4000)}',
        ]
        trace = traceback.format_exc().strip()
        if trace and trace != 'NoneType: None':
            diagnostic_lines.append(f'Traceback:\n{self._truncate_diagnostic_value(trace, 12000)}')

        self.emit_diagnostic({
            'name': 'genericError',
            'message': '\n'.join(diagnostic_lines),
        })

    # -------------------------------------------------------------------------
    # Input Methods
    # -------------------------------------------------------------------------
    
    def connect(self) -> None:
        """
        Establish connection with parent process and start listening for messages.
        
        Sends initial worker identification message, then enters the main
        message processing loop.
        """
        log('Connecting to parent process')
        # Send initial connection message
        self.send({'worker': str(self._id)})
        
        # Start listening for messages
        log('Starting message listener')
        self._listen()
    
    def _listen(self) -> None:
        """
        Main message processing loop.
        
        Reads from stdin, buffers data, and processes complete messages
        as they arrive.
        """
        try:
            while True:
                # Read data from stdin
                data = sys.stdin.read(1)
                if not data:
                    # EOF reached
                    break
                
                self._buffer += data
                
                # Process complete messages in the buffer
                self._process_buffer()
                
        except KeyboardInterrupt:
            pass
        except Exception as e:
            self.report_error(e)
    
    def _process_buffer(self) -> None:
        """
        Process complete messages from the buffer.
        
        Extracts messages delimited by MESSAGE_START and MESSAGE_END markers,
        parses them as JSON, and dispatches to appropriate handlers.
        """
        while True:
            start = self._buffer.find(MESSAGE_START)
            if start == -1:
                break
            
            end = self._buffer.find(MESSAGE_END, start)
            if end == -1:
                break
            
            try:
                # Extract message content
                message_content = self._buffer[start + len(MESSAGE_START):end].strip()
                message = json.loads(message_content)
                
                # Dispatch to handler
                message_type = message.get('type')
                message_data = message.get('data')
                
                log(f'Received message type: {message_type}')
                
                if message_type in self._handlers:
                    self._handlers[message_type](message_data)
                else:
                    self.report_error(f'Unknown message type: {message_type}')
                    
            except json.JSONDecodeError as e:
                self.report_error(f'Failed to parse message: {e}')
            except Exception as e:
                self.report_error(e)
            finally:
                # Remove processed message from buffer
                self._buffer = self._buffer[end + len(MESSAGE_END):]

    # -------------------------------------------------------------------------
    # Message Handlers
    # -------------------------------------------------------------------------
    
    def _on_connected(self, data: Any) -> None:
        """Handle 'in:connected' message."""
        log('Connection confirmed by parent')
    
    def _on_ping(self, data: Any) -> None:
        """Handle 'in:ping' message - respond with pong."""
        log(f'Received ping: {data}')
        self.send({'type': 'pong', 'data': data})
    
    def _on_run(self, config: Dict[str, Any]) -> None:
        """
        Handle 'in:run' message - execute test run.
        
        Args:
            config: Test run configuration
        """
        log(f'Run requested with config keys: {list(config.keys()) if config else None}')
        
        self._config = config
        self._session_id = config.get('sessionId')
        self._project_root = config.get('localProjectDir')
        self._reported_global_errors.clear()
        
        # Build file path to ID mapping from config
        self._build_file_mappings(config)
        
        # Configure tracer with run settings
        if self._tracer:
            self._tracer.set_session(self._session_id)
            self._tracer.reset()

            # Set tracer configuration from config
            self._tracer._hints = config.get('hints', {})
            self._tracer._auto_console_log = config.get('autoConsoleLog', True)
            self._tracer._capture_console_log = config.get('captureConsoleLog', True)
            self._tracer.set_log_limits(config.get('logLimits', self._log_limits))
            self._tracer._max_log_entry_size = config.get('maxLogEntrySize', 16384)
            self._tracer._max_trace_steps = config.get('maxTraceSteps', 999999)
            self._tracer._max_trace_steps_for_watch_expression_prefetch = config.get(
                'maxTraceStepsForWatchExpressionPrefetch',
                10,
            )
            self._tracer._expressions_to_evaluate = config.get('expressionsToEvaluate', {})
            self._tracer.set_selected_tests(config.get('tests'))
            
            # Initialize trace recording if traceContext is provided
            trace_context = config.get('traceContext')
            if trace_context:
                self._tracer.init_trace(trace_context)
            
            # Initialize test files
            test_files = config.get('testFiles', [])
            self._tracer.init_loading_phase(test_files)
            
            # Notify run received
            self._tracer.run_received()
            
            # Mark receiver as ready now that we have run config
            self._tracer.set_receiver_ready()
        
        # Execute tests using pytest
        try:
            log('Received in:run message, starting test execution')
            self._set_execution_stage('run_received')
            self._current_test_paths = []
            self._execute_tests(config)
        except Exception as e:
            log(f'Error executing tests: {e}\n{traceback.format_exc()}')
            self._emit_runtime_error_diagnostic(
                'Python worker failed while executing tests.',
                e,
                config,
            )
            if self._tracer:
                self._tracer.report_global_error(e)
        finally:
            self._set_execution_stage('idle')
            self._current_test_paths = []
    
    def _build_file_mappings(self, config: Dict[str, Any]) -> None:
        """
        Build file path to ID mappings and file metadata from config.
        
        Files are sent incrementally - only changed files are included in each run.
        This method applies the delta to the persistent cache and mappings.
        """
        local_project_dir = config.get('localProjectDir', '')
        
        # Process deletions - update cache and mappings together
        for rel_path in config.get('deletedFiles', []):
            file_info = self._files_cache.pop(rel_path, None)
            if file_info:
                abs_path = os.path.join(local_project_dir, rel_path) if not os.path.isabs(rel_path) else rel_path
                normalized = str(Path(abs_path).resolve())
                self._file_path_to_id.pop(normalized, None)
                self._file_metadata.pop(normalized, None)
                self._log_markers_by_path.pop(normalized, None)
                file_id = file_info.get('id')
                if file_id is not None:
                    self._test_file_ids.discard(file_id)
        
        # Process updates/additions - update cache and mappings together
        for file_info in config.get('files', []):
            rel_path = file_info.get('path')
            if not rel_path:
                continue
            
            self._files_cache[rel_path] = file_info
            
            file_id = file_info.get('id')
            if file_id is None:
                continue
            
            is_test = file_info.get('test', False)
            
            abs_path = os.path.join(local_project_dir, rel_path) if not os.path.isabs(rel_path) else rel_path
            normalized = str(Path(abs_path).resolve())
            
            self._file_path_to_id[normalized] = file_id
            self._file_metadata[normalized] = {
                'id': file_id,
                'path': rel_path,
                'inOriginalFilesCache': file_info.get('inOriginalFilesCache', False),
            }

            if 'logMarkers' in file_info:
                self._log_markers_by_path[normalized] = file_info.get('logMarkers') or []
            
            if is_test:
                self._test_file_ids.add(file_id)
            else:
                self._test_file_ids.discard(file_id)
        
        # Process test files for this run
        for tf in config.get('testFiles', []):
            file_id = tf.get('id')
            rel_path = tf.get('path', '')
            if file_id is None or not rel_path:
                continue
                
            abs_path = os.path.join(local_project_dir, rel_path) if not os.path.isabs(rel_path) else rel_path
            normalized = str(Path(abs_path).resolve())
            
            self._file_path_to_id[normalized] = file_id
            self._test_file_ids.add(file_id)
            
            if normalized not in self._file_metadata:
                self._file_metadata[normalized] = {
                    'id': file_id,
                    'path': rel_path,
                }

    def _report_global_error_once(self, key: str, error_obj: Dict[str, Any]) -> None:
        if key in self._reported_global_errors:
            return
        self._reported_global_errors.add(key)
        if self._tracer:
            self._tracer.report_global_error(error_obj)

    def _format_syntax_error_message(self, path: str, error: Exception, content: str) -> Dict[str, Any]:
        rel_path = path
        if self._project_root and path.startswith(self._project_root):
            rel_path = path[len(self._project_root):].lstrip(os.sep)

        if isinstance(error, SyntaxError) or isinstance(error, tokenize.TokenError):
            lines = content.splitlines()

            if isinstance(error, tokenize.TokenError):
                message = error.args[0] if error.args else "SyntaxError"
                lineno = 1
                offset = 1
                if len(error.args) > 1 and isinstance(error.args[1], tuple):
                    lineno = error.args[1][0] or 1
                    col = error.args[1][1] or 0
                    offset = col + 1
                line_text = lines[lineno - 1] if lineno - 1 < len(lines) else ""
            else:
                lineno = error.lineno or 1
                offset = error.offset or 1
                message = error.msg or "SyntaxError"
                line_text = error.text.strip("\n") if error.text else (lines[lineno - 1] if lineno - 1 < len(lines) else "")

            start_line = max(1, lineno - 1)
            end_line = min(len(lines), lineno + 1) if lines else lineno
            frame_lines: list[str] = []

            for i in range(start_line, end_line + 1):
                prefix = ">" if i == lineno else " "
                line_content = lines[i - 1] if i - 1 < len(lines) else ""
                frame_lines.append(f"{prefix} {i} | {line_content}")
                if i == lineno:
                    caret = " " * max(offset - 1, 0)
                    frame_lines.append(f"  | {caret}^ SyntaxError: {message} ({lineno}:{offset})")

            code_frame = "\n".join(frame_lines)
            error_message = f"Failed to instrument {rel_path}\n{code_frame}"
            stack = (
                f'Traceback (most recent call last):\n'
                f'  File \"{path}\", line {lineno}, in <module>\n'
                f'SyntaxError: {message}'
            )
            return {"message": error_message, "stack": stack}

        # Fallback for non-syntax errors
        return {"message": f"Failed to instrument {rel_path}: {error}", "stack": traceback.format_exc()}
    
    def _framework_name(self) -> str:
        return (self._framework_version or "pytest@1.0.0").split("@")[0]

    def _execute_tests(self, config: Dict[str, Any]) -> None:
        """
        Execute the test run using the configured Python framework.
        
        Args:
            config: Test run configuration
        """
        if not self._tracer:
            return
        
        self._set_execution_stage('starting_test_execution')
        log('Starting test execution')
        
        # Log Python environment info for debugging
        log_python_environment()
        
        project_root = config.get('localProjectDir', os.getcwd())
        self._set_execution_stage('configuring_environment')
        
        # Configure virtual environment (this is a fallback if not already in venv)
        # When the venv's Python is used directly, this will short-circuit early
        configure_virtual_environment(project_root)
        
        # Add project root to sys.path
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        
        # Add src/ to sys.path for src-layout projects (where src/ is a
        # namespace directory without __init__.py, not a package itself)
        src_dir = os.path.join(project_root, 'src')
        if (os.path.isdir(src_dir)
                and not os.path.isfile(os.path.join(src_dir, '__init__.py'))
                and src_dir not in sys.path):
            sys.path.insert(1, src_dir)
            log(f'Added src directory to sys.path: {src_dir}')

        if not self._run_initializer_if_needed(config):
            return
        
        # Now import runner modules (after sys.path and venv are configured)
        self._set_execution_stage('loading_runner_adapter')
        from runner.adapters.wallaby_adapter import WallabyEventAdapter
        
        # Create Wallaby event adapter
        wallaby_adapter = WallabyEventAdapter(
            tracer=self._tracer,
            file_path_to_id=self._file_path_to_id,
            test_file_ids=self._test_file_ids,
            project_root=project_root,
            log=log,
        )

        def log_marker_provider(path: str) -> list[dict[str, Any]]:
            normalized = str(Path(path).resolve())
            return self._log_markers_by_path.get(normalized, [])

        def on_transform_error(path: str, error: Exception, content: str) -> None:
            if not path:
                return
            if self._project_root and not path.startswith(self._project_root):
                return
            if not isinstance(error, (SyntaxError, tokenize.TokenError)) and not _error_origin_matches_path(
                path,
                error,
                self._project_root,
            ):
                return
            error_obj = self._format_syntax_error_message(path, error, content)
            error_key = f"transform:{path}:{type(error).__name__}:{getattr(error, 'lineno', '')}:{getattr(error, 'offset', '')}"
            self._report_global_error_once(error_key, error_obj)

        plugin = None
        started_reported = False

        def report_started() -> None:
            nonlocal started_reported
            if started_reported:
                return
            self._tracer.started({})
            started_reported = True

        def on_exec_error(path: str, error: Exception) -> None:
            current_test_id = getattr(plugin, '_current_test', None) if plugin is not None else None
            if not _should_report_exec_error(path, error, self._project_root, framework_name, current_test_id):
                return
            if not _error_origin_matches_path(path, error, self._project_root):
                return
            error_key = f"exec:{path}:{type(error).__name__}:{error}"
            self._report_global_error_once(error_key, {'message': str(error), 'stack': traceback.format_exc()})
        
        # Get test files to run
        test_files = config.get('testFiles', [])
        if not test_files:
            log('No test files to run')
            self._tracer.started({})
            self._tracer.complete({})
            return
        
        # Build list of test file paths
        self._set_execution_stage('resolving_test_paths')
        test_paths = []
        for tf in test_files:
            file_path = tf.get('normalizedRelativePath', '')
            if file_path:
                if not os.path.isabs(file_path):
                    abs_path = os.path.join(project_root, file_path)
                else:
                    abs_path = file_path
                test_paths.append(abs_path)

        framework_name = self._framework_name()
        if framework_name == 'pytest':
            filtered_test_paths = _filter_pytest_test_paths(test_paths, project_root)
            skipped_test_paths = [path for path in test_paths if path not in filtered_test_paths]
            if skipped_test_paths:
                log(f'Skipping non-collectable pytest targets: {skipped_test_paths}')
            test_paths = filtered_test_paths

        self._current_test_paths = test_paths.copy()

        log(f'Running tests in: {test_paths}')

        log(f'Using Python test framework: {framework_name} ({self._framework_version})')

        if not test_paths:
            log('No collectable test files to run after filtering')
            self._tracer.started({})
            self._tracer.complete({})
            return

        self._set_execution_stage('creating_framework_plugin')
        if framework_name == 'unittest':
            from runner.adapters.unittest_plugin import InstrumentedUnittestAdapter

            plugin = InstrumentedUnittestAdapter(
                project_root=project_root,
                enable_coverage=True,
                enable_value_logging=True,
                selected_tests=config.get('tests'),
                include_paths=['src', 'tests', 'test'],
                exclude_paths=['.venv', 'venv', 'node_modules', '__pycache__', '.git'],
                hints=config.get('hints', {}),
                on_coverage_hit=wallaby_adapter.record_coverage_hit,
                on_value_logged=wallaby_adapter.record_value_log,
                on_time_logged=wallaby_adapter.record_time_log,
                on_test_call_start=wallaby_adapter.on_test_call_start,
                on_print_called=wallaby_adapter.record_print_call,
                on_logpoint_called=wallaby_adapter.record_logpoint_call,
                log=log,
            )
        else:
            from runner.adapters.pytest_plugin import InstrumentedTestPlugin

            # Create pytest plugin with instrumentation
            # We'll set the on_coverage_hit callback after creating the wallaby adapter
            plugin = InstrumentedTestPlugin(
                project_root=project_root,
                enable_coverage=True,
                enable_value_logging=True,
                selected_tests=config.get('tests'),
                include_paths=['src', 'tests', 'test'],
                exclude_paths=['.venv', 'venv', 'node_modules', '__pycache__', '.git'],
                hints=config.get('hints', {}),
                on_coverage_hit=wallaby_adapter.record_coverage_hit,
                on_value_logged=wallaby_adapter.record_value_log,
                on_time_logged=wallaby_adapter.record_time_log,
                on_test_call_start=wallaby_adapter.on_test_call_start,
                on_print_called=wallaby_adapter.record_print_call,
                on_logpoint_called=wallaby_adapter.record_logpoint_call,
                on_loading_complete=report_started,
                log=log,
            )
        
        # Connect our Wallaby adapter to receive events
        plugin.session.event_adapter = wallaby_adapter
        plugin.session.log_marker_provider = log_marker_provider
        plugin.session.on_used_logpoints = wallaby_adapter.report_used_logpoints
        plugin.session.on_transform_error = on_transform_error
        plugin.session.on_exec_error = on_exec_error
        
        # Set up content provider for cached files
        if self._originalCacheRoot:
            content_provider = WallabyContentProvider(
                files_cache=self._files_cache,
                originalCacheRoot=self._originalCacheRoot,
                file_metadata_by_path=self._file_metadata,
                project_root=self._project_root,
                log_func=log,
            )
            plugin.session.content_provider = content_provider
        
        # Signal test execution started. For pytest, this is delayed until
        # collection finishes so loadingSequence includes imported source files.
        if framework_name == 'unittest':
            report_started()
        
        # Start instrumentation session
        self._set_execution_stage('starting_instrumentation_session')
        plugin.session.start()

        try:
            # Ensure changed project modules are re-imported on each run
            self._set_execution_stage('clearing_project_modules')
            clear_project_modules(project_root)

            if framework_name == 'unittest':
                self._set_execution_stage('running_unittest')
                exit_code = plugin.run(test_paths)
                log(f'Unittest exit code: {exit_code}')
            else:
                import pytest

                # Build pytest arguments
                pytest_args = test_paths.copy()

                # Add standard flags for Wallaby integration
                pytest_args.extend([
                    '-v',            # Verbose for better test names
                    '--tb=short',    # Short tracebacks
                    '--no-header',   # No header
                    '-p', 'no:cacheprovider',  # Disable cache
                ])

                log(f'Pytest args: {pytest_args}')

                # Capture stdout/stderr during pytest run
                self._set_execution_stage('running_pytest')
                old_stdout = sys.stdout
                old_stderr = sys.stderr

                # Redirect to devnull to prevent pytest output from mixing with IPC
                sys.stdout = open(os.devnull, 'w')
                sys.stderr = open(os.devnull, 'w')

                try:
                    exit_code = pytest.main(pytest_args, plugins=[plugin])
                    log(f'Pytest exit code: {exit_code}')
                finally:
                    sys.stdout.close()
                    sys.stderr.close()
                    sys.stdout = old_stdout
                    sys.stderr = old_stderr

                report_started()

        except ImportError as e:
            report_started()
            if framework_name == 'unittest':
                log(f'Unittest import/setup error: {e}')
                self._emit_runtime_error_diagnostic(
                    'Python unittest adapter could not be initialized for this project.',
                    e,
                    config,
                )
                self._tracer.report_global_error({
                    'message': 'unittest could not be initialized for this project.',
                    'stack': traceback.format_exc(),
                })
            else:
                log(f'Pytest not available: {e}')
                self._emit_runtime_error_diagnostic(
                    'Pytest could not be initialized for this project.',
                    e,
                    config,
                )
                self._tracer.report_global_error({
                    'message': 'pytest is not installed. Please install pytest to run Python tests.',
                    'stack': traceback.format_exc(),
                })
        
        except Exception as e:
            log(f'Error running {framework_name}: {e}\n{traceback.format_exc()}')
            self._emit_runtime_error_diagnostic(
                f'Python {framework_name} execution failed.',
                e,
                config,
            )
            self._tracer.report_global_error(e)
        
        finally:
            # Stop instrumentation
            self._set_execution_stage('stopping_instrumentation_session')
            plugin.session.stop()
            log('Test execution finished, instrumentation stopped')
        
        # Signal completion
        self._set_execution_stage('sending_complete')
        log('Sending tracer complete')
        self._tracer.complete({})
    
    def _on_stop(self, request_id: Any) -> None:
        """
        Handle 'in:stop' message - stop current run and cleanup.
        
        Args:
            request_id: Request identifier for tracking
        """
        log(f'Stop requested with request_id: {request_id}')
        
        # Reset tracer state
        if self._tracer:
            self._tracer.reset()
        
        self.send({'type': 'closed', 'data': {'requestId': request_id, 'error': False}})
    
    def _on_teardown(self, data: Any) -> None:
        """Handle 'in:teardown' message."""
        log('Teardown requested')

        teardown_error = None

        if self._initializer_teardown is not None:
            try:
                self._initializer_teardown()
            except Exception as error:
                teardown_error = error

        config = self._config if isinstance(self._config, dict) else {}
        teardown_target = config.get('teardown') if isinstance(config, dict) else None
        if isinstance(teardown_target, str) and teardown_target.strip():
            try:
                self._invoke_hook(teardown_target.strip(), 'teardown', config)
            except Exception as error:
                teardown_error = teardown_error or error

        if teardown_error is not None:
            self._emit_runtime_error_diagnostic(
                'Python worker teardown hook failed.',
                teardown_error,
                config,
                extra={'teardownHook': teardown_target or self._active_initializer},
            )
            if self._tracer:
                self._tracer.report_global_error(teardown_error)

        self._initializer_teardown = None
        self._initializer_ran = False
        self._active_initializer = None
        
        # Cleanup tracer
        if self._tracer:
            self._tracer.restore_console()
    
    def _on_tracer_resume(self, data: Any) -> None:
        """Handle 'in:tracer.resume' message."""
        log('Tracer resume requested')
        # Resume is used when debugging - currently a no-op


def main():
    """
    Entry point for the Python test worker.
    
    Expected command line arguments:
    - worker_id: Unique identifier for this worker instance
    - Additional arguments as needed for test framework configuration
    """
    log(f'Python test worker starting with args: {sys.argv}')
    
    if len(sys.argv) < 2:
        print('Usage: pythonTestWorker.py <worker_id> [additional_args...]', file=sys.stderr)
        sys.exit(1)
    
    worker_id = sys.argv[1]
    framework_version = sys.argv[2] if len(sys.argv) >= 3 else "pytest@1.0.0"
    originalCacheRoot = sys.argv[4]
    worker_log_limits: Optional[Dict[str, Any]] = None
    if len(sys.argv) >= 7 and sys.argv[6]:
        try:
            parsed_limits = json.loads(sys.argv[6])
            if isinstance(parsed_limits, dict):
                worker_log_limits = parsed_limits
        except Exception:
            worker_log_limits = None

    try:
        # Create and connect worker
        worker = TestWorker(worker_id, originalCacheRoot, worker_log_limits, framework_version)
        worker.connect()
    except Exception as e:
        # Log any crash details
        log(f'FATAL ERROR: {type(e).__name__}: {e}')
        log(f'Traceback:\n{traceback.format_exc()}')
        raise
    finally:
        # Cleanup tracer on exit
        log('Worker exiting, cleaning up tracer')
        destroy_tracer()


if __name__ == '__main__':
    main()
