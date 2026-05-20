from __future__ import annotations

import atexit
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Iterable


def is_django_project() -> bool:
    return bool(os.environ.get('DJANGO_SETTINGS_MODULE'))


def patch_unittest_adapter(module: ModuleType) -> None:
    adapter_class = module.InstrumentedUnittestAdapter
    if getattr(adapter_class, '_wallaby_django_patched', False):
        return

    original_run = adapter_class.run

    def run(self, test_paths):
        if not is_django_project():
            return original_run(self, test_paths)

        return _run_django_unittest(module, self, test_paths)

    adapter_class.run = run
    adapter_class._wallaby_django_patched = True


def _collect_test_infos(module: ModuleType, adapter, suite) -> None:
    collected = list(adapter._iter_tests(suite))
    test_infos = []
    for test in collected:
        file_path = adapter._get_test_file_path(test)
        test_infos.append(
            module.TestInfo(
                test_id=adapter._build_test_id(test, file_path),
                test_name=adapter._get_test_name(test),
                file_path=file_path,
                line_number=adapter._get_test_line(test),
            )
        )

    adapter.events.emit(module.TestsCollectedEvent(tests=test_infos))


class _DjangoState:
    """Holds one-time Django bootstrap state for a worker process."""

    __slots__ = (
        'bootstrapped', 'test_runner', 'old_db_config',
        'added_paths', 'previous_settings',
    )

    def __init__(self) -> None:
        self.bootstrapped: bool = False
        self.test_runner = None
        self.old_db_config = None
        self.added_paths: list[str] = []
        self.previous_settings: str | None = None


def _get_or_create_state(adapter) -> _DjangoState:
    attr = '_wallaby_django_state'
    state = getattr(adapter, attr, None)
    if state is None:
        state = _DjangoState()
        setattr(adapter, attr, state)
    return state


def _ensure_sys_path(path: Path) -> bool:
    normalized_path = str(path)
    if normalized_path in sys.path:
        return False
    sys.path.insert(0, normalized_path)
    return True


def _get_test_root_path(project_root: Path) -> Path | None:
    value = os.environ.get('WALLABY_DJANGO_TEST_ROOT')
    if not isinstance(value, str) or not value.strip():
        return None

    candidate = (project_root / value).resolve()
    return candidate if candidate.exists() else None


def _bootstrap_django(adapter, state: _DjangoState, test_root: Path | None) -> None:
    """One-time Django bootstrap per worker process.

    Sets up the Django environment, runs django.setup(), creates a
    DiscoverRunner, sets up test databases, and registers an atexit
    handler for cleanup.
    """
    project_root = Path(adapter._project_root).resolve()

    # Stop the Wallaby instrumentation session - its import hooks interfere
    # with Django's runtime behaviour.
    if getattr(adapter, 'session', None) and getattr(adapter.session, '_started', False):
        adapter.session.stop()

    # Ensure project root is on sys.path
    if _ensure_sys_path(project_root):
        state.added_paths.append(str(project_root))

    if test_root is not None and _ensure_sys_path(test_root):
        state.added_paths.append(str(test_root))

    # DJANGO_SETTINGS_MODULE should already be set via env from the configurator
    state.previous_settings = os.environ.get('DJANGO_SETTINGS_MODULE')

    import django
    django.setup()

    from django.test.runner import DiscoverRunner

    state.test_runner = DiscoverRunner(
        verbosity=0,
        interactive=False,
        failfast=False,
        keepdb=False,
        reverse=False,
        debug_sql=False,
        parallel=1,
        tags=None,
        exclude_tags=None,
        test_name_patterns=None,
        pdb=False,
        buffer=False,
        timing=False,
        shuffle=False,
    )

    state.test_runner.setup_test_environment()

    from django.conf import settings as dj_settings

    databases = {alias: True for alias in dj_settings.DATABASES}
    state.old_db_config = state.test_runner.setup_databases(
        aliases=databases,
        serialized_aliases=set(databases.keys()),
    )
    state.test_runner.run_checks(databases)

    state.bootstrapped = True

    atexit.register(_teardown_django, state)


def _teardown_django(state: _DjangoState) -> None:
    """Atexit handler - tears down databases and restores environment."""
    try:
        if state.old_db_config is not None:
            state.test_runner.teardown_databases(state.old_db_config)
    except Exception:
        pass
    try:
        if state.test_runner is not None:
            state.test_runner.teardown_test_environment()
    except Exception:
        pass
    for p in reversed(state.added_paths):
        try:
            sys.path.remove(p)
        except ValueError:
            pass


def _resolve_test_labels(project_root: Path, test_paths: Iterable[str], test_root: Path | None = None) -> list[str]:
    """Convert file paths to Django test labels (dotted module paths)."""
    root_for_labels = test_root or project_root
    labels: list[str] = []
    seen: set[str] = set()

    for raw_path in test_paths:
        candidate = Path(raw_path).resolve()
        try:
            relative_path = candidate.relative_to(root_for_labels)
        except ValueError:
            continue

        path_parts = list(relative_path.parts)
        if not path_parts:
            continue

        if candidate.is_dir():
            label_parts = path_parts
        else:
            file_name = path_parts[-1]
            stem = candidate.stem
            if file_name == '__init__.py':
                label_parts = path_parts[:-1]
            elif file_name.startswith('test_') or file_name.endswith('_test.py') or file_name == 'tests.py':
                label_parts = [*path_parts[:-1], stem]
            else:
                label_parts = path_parts[:-1]

        label = '.'.join(part for part in label_parts if part)
        if not label or label in seen:
            continue

        labels.append(label)
        seen.add(label)

    return labels


def _run_django_unittest(module: ModuleType, adapter, test_paths) -> int:
    project_root = Path(adapter._project_root).resolve()
    test_root = _get_test_root_path(project_root)
    labels = _resolve_test_labels(project_root, test_paths, test_root)
    if not labels:
        return 0

    state = _get_or_create_state(adapter)
    if not state.bootstrapped:
        _bootstrap_django(adapter, state, test_root)

    suite = _build_suite_safe(state.test_runner, labels)
    if suite.countTestCases() == 0:
        return 0

    _collect_test_infos(module, adapter, suite)

    result = module._WallabyUnittestResult(adapter)
    suite.run(result)
    adapter._finalize_current_file()

    return 0 if result.wasSuccessful() else 1


def _build_suite_safe(test_runner, labels: list[str]):
    """Build a test suite, isolating per-label import failures."""
    import unittest as _unittest

    try:
        suite = test_runner.build_suite(labels)
    except Exception:
        suite = _unittest.TestSuite()
        for label in labels:
            try:
                suite.addTests(test_runner.build_suite([label]))
            except Exception:
                pass

    return _deduplicate_suite(suite)


def _iter_all_tests(suite):
    """Recursively yield individual test cases from a (possibly nested) suite."""
    for test in suite:
        if isinstance(test, __import__('unittest').TestSuite):
            yield from _iter_all_tests(test)
        else:
            yield test


def _deduplicate_suite(suite):
    """Return a flat suite with duplicate test cases removed.

    Python's ``TestLoader.loadTestsFromModule`` discovers every ``TestCase``
    subclass that is *visible* in a module's namespace, including ones that
    were merely *imported* there (e.g. ``from .test_foo import FooTest``).
    When multiple test modules import the same base test class, Django's
    ``build_suite`` adds that class's tests once per importing module, causing
    each logical test to appear several times in the combined suite.

    We deduplicate using ``test.id()`` which returns the canonical
    dotted name ``module.Class.method`` — identical for every copy of the
    same logical test regardless of which module it was discovered through.
    """
    import unittest as _unittest

    seen: set[str] = set()
    deduped = _unittest.TestSuite()
    for test in _iter_all_tests(suite):
        tid = test.id()
        if tid not in seen:
            seen.add(tid)
            deduped.addTest(test)
    return deduped
