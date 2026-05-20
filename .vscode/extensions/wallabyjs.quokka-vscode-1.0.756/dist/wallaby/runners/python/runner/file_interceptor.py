from __future__ import annotations

"""File interception for cached file content."""

import importlib.abc
import importlib.machinery
import importlib.util
import sys
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable, Protocol, runtime_checkable

from .transformer import CodeTransformer
from .source_map import SourceMap


@runtime_checkable
class ContentProvider(Protocol):
    """
    Protocol for providing file content on demand.
    
    Implement this to provide cached file content from an alternate
    disk location (e.g., Wallaby's cache directory).
    """
    
    def get_cached_content(self, path: str) -> Optional[str]:
        """
        Get cached content for a file path if available.
        
        This method should:
        1. Look up the file in the cache
        2. If found, read content from the cache location
        3. Return the content, or None if not in cache
        
        Args:
            path: The normalized absolute path to the file
            
        Returns:
            The cached content if available, None otherwise
        """
        ...


@dataclass
class FileInterceptor:
    """
    Intercepts file reads to provide cached file content.
    Also handles code transformation during import.
    
    To provide cached content, set a content_provider that implements
    the ContentProvider protocol:
    
        class MyContentProvider:
            def __init__(self, file_metadata: dict, cache_dir: str):
                self.file_metadata = file_metadata
                self.cache_dir = cache_dir
            
            def get_cached_content(self, path: str) -> Optional[str]:
                file_info = self.file_metadata.get(path)
                if file_info:
                    cache_path = os.path.join(self.cache_dir, file_info['relative_path'])
                    with open(cache_path, 'r') as f:
                        return f.read()
                return None
        
        interceptor.content_provider = MyContentProvider(metadata, '/path/to/cache')
    """
    
    transformer: Optional[CodeTransformer] = None
    source_maps: dict[str, SourceMap] = field(default_factory=dict)
    content_provider: Optional[ContentProvider] = None
    on_file_loaded: Optional[Callable[[str], None]] = None  # Callback when file is loaded
    on_file_transformed: Optional[Callable[[str, SourceMap], None]] = None  # Callback when file is transformed
    on_transform_error: Optional[Callable[[str, Exception, str], None]] = None  # Callback when transform fails
    on_exec_error: Optional[Callable[[str, Exception], None]] = None  # Callback when exec fails
    on_used_logpoints: Optional[Callable[[str, list[str]], None]] = None  # Callback when logpoints used
    log_marker_provider: Optional[Callable[[str], list[dict]]] = None  # Provide log markers for a file
    _original_open: Optional[Callable] = None
    _installed: bool = False
    
    def get_content(self, path: str) -> str:
        """
        Get file content, checking sources in order:
        1. Content provider (for cached content)
        2. Disk (original file)
        
        Returns the file content.
        """
        normalized_path = str(Path(path).resolve())
        
        # 1. Check content provider for cached content
        if self.content_provider:
            content = self.content_provider.get_cached_content(normalized_path)
            if content is not None:
                return content
        
        # 2. Read from disk
        with open(normalized_path, "r", encoding="utf-8") as f:
            return f.read()
    
    def get_source_map(self, path: str) -> Optional[SourceMap]:
        """Get the source map for a transformed file."""
        normalized_path = str(Path(path).resolve())
        return self.source_maps.get(normalized_path)
    
    def install_import_hook(self, paths_to_intercept: Optional[list[str]] = None) -> None:
        """Install the import hook to intercept module loading."""
        if self._installed:
            return
        
        finder = InterceptingFinder(self, paths_to_intercept)
        sys.meta_path.insert(0, finder)
        self._installed = True
    
    def uninstall_import_hook(self) -> None:
        """Remove the import hook."""
        sys.meta_path = [
            finder for finder in sys.meta_path
            if not isinstance(finder, InterceptingFinder)
        ]
        self._installed = False
    
    def transform_and_cache(self, path: str, content: str) -> tuple[str, SourceMap, object]:
        """Transform content and cache the source map."""
        if self.transformer:
            log_markers = self.log_marker_provider(path) if self.log_marker_provider else None
            try:
                code, transformed, source_map = self.transformer.transform_for_exec(
                    content,
                    path,
                    log_markers=log_markers,
                )
            except Exception as error:
                if self.on_transform_error:
                    self.on_transform_error(path, error, content)
                raise
            self.source_maps[path] = source_map
            # Notify about transformation (for registering coverage lines)
            if self.on_file_transformed:
                self.on_file_transformed(path, source_map)
            if self.on_used_logpoints:
                used_logpoints = getattr(source_map, "used_logpoints", None)
                if used_logpoints:
                    self.on_used_logpoints(path, list(used_logpoints))
            return transformed, source_map, code
        else:
            # No transformation, create identity source map
            source_map = SourceMap(source_file=path, original_source=content)
            lines = content.splitlines()
            for i, line in enumerate(lines, start=1):
                source_map.add_original_line(i, line)
            source_map.finalize()
            self.source_maps[path] = source_map
            code = compile(content, path, "exec")
            return content, source_map, code


class InterceptingFinder(importlib.abc.MetaPathFinder):
    """Custom finder that intercepts imports for specified paths."""
    
    def __init__(
        self,
        interceptor: FileInterceptor,
        paths_to_intercept: Optional[list[str]] = None,
    ):
        self.interceptor = interceptor
        self.paths_to_intercept = [
            str(Path(p).resolve()) for p in (paths_to_intercept or [])
        ]
    
    def _should_intercept(self, path: str) -> bool:
        """Check if the given path should be intercepted."""
        if not path:
            return False
        
        resolved = str(Path(path).resolve())
        
        # Never intercept site-packages or standard library
        if "site-packages" in resolved or "lib/python" in resolved:
            return False
        
        # Check if path is under any intercepted directory
        if self.paths_to_intercept:
            for intercept_path in self.paths_to_intercept:
                if resolved.startswith(intercept_path):
                    return True
            return False
        
        return True  # Intercept everything if no specific paths set
    
    def find_spec(
        self,
        fullname: str,
        path: Optional[list[str]],
        target: Optional[object] = None,
    ) -> Optional[importlib.machinery.ModuleSpec]:
        """Find module spec, intercepting if needed."""
        # Skip built-in and frozen modules
        if fullname in sys.builtin_module_names:
            return None

        # Python import names are dotted identifiers, not file-system paths.
        # Reject path-like names so we don't accidentally make invalid imports
        # such as `cliapp/app` importable just because the file exists on disk.
        if "/" in fullname or "\\" in fullname:
            return None
        
        # Determine search paths
        # For submodules (path is set by parent package), use that path
        # For top-level modules, use sys.path
        search_paths = path if path else sys.path
        
        # Get the simple module name (last part of dotted name)
        parts = fullname.split(".")
        simple_name = parts[-1]
        
        for search_path in search_paths:
            # Check for package (directory with __init__.py)
            package_dir = os.path.join(search_path, simple_name)
            package_init = os.path.join(package_dir, "__init__.py")
            if os.path.isfile(package_init) and self._should_intercept(package_init):
                return self._create_spec(fullname, package_init, is_package=True)
            
            # Check for module file
            module_file = os.path.join(search_path, simple_name + ".py")
            if os.path.isfile(module_file) and self._should_intercept(module_file):
                return self._create_spec(fullname, module_file, is_package=False)
        
        return None
    
    def _create_spec(
        self,
        fullname: str,
        path: str,
        is_package: bool,
    ) -> importlib.machinery.ModuleSpec:
        """Create a module spec with our custom loader."""
        loader = InterceptingLoader(self.interceptor, path)
        spec = importlib.machinery.ModuleSpec(
            fullname,
            loader,
            origin=path,
            is_package=is_package,
        )
        if is_package:
            spec.submodule_search_locations = [os.path.dirname(path)]
        return spec


class InterceptingLoader(importlib.abc.Loader):
    """Custom loader that uses intercepted/transformed content."""
    
    def __init__(self, interceptor: FileInterceptor, path: str):
        self.interceptor = interceptor
        self.path = path
    
    def create_module(self, spec: importlib.machinery.ModuleSpec) -> None:
        """Use default module creation."""
        return None
    
    def exec_module(self, module: object) -> None:
        """Execute module with intercepted/transformed content."""
        module.__file__ = self.path
        if getattr(module, "__spec__", None) is not None:
            module.__loader__ = self
            module.__package__ = module.__spec__.parent
            module.__cached__ = None

        content = self.interceptor.get_content(self.path)
        
        # Emit file loaded event
        if self.interceptor.on_file_loaded:
            self.interceptor.on_file_loaded(self.path)
        
        transformed, _, code = self.interceptor.transform_and_cache(self.path, content)

        # Execute compiled code
        try:
            exec(code, module.__dict__)
        except Exception as error:
            if self.interceptor.on_exec_error:
                self.interceptor.on_exec_error(self.path, error)
            raise
    
    def get_source(self, fullname: str) -> str:
        """Return the (possibly transformed) source."""
        content = self.interceptor.get_content(self.path)
        transformed, _, _ = self.interceptor.transform_and_cache(self.path, content)
        return transformed

    def is_package(self, fullname: str) -> bool:
        """PEP 302 compatibility hook used by some libraries (for example Flask)."""
        return os.path.basename(self.path) == "__init__.py"

    def get_filename(self, fullname: str) -> str:
        """Return the underlying module file path for inspect-based callers."""
        return self.path
