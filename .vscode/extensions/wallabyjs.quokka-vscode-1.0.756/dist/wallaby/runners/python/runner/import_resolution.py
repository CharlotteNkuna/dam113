from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModuleImportContext:
    module_name: str
    package_name: str
    sys_path_entry: str
    is_package: bool


def _find_top_level_package_dir(start_dir: Path) -> Path | None:
    package_root: Path | None = None
    current = start_dir.resolve()

    while True:
        if not (current / "__init__.py").is_file():
            return package_root
        package_root = current
        if current.parent == current:
            return package_root
        current = current.parent


def resolve_module_import_context(file_path: str | Path, project_root: str | Path) -> ModuleImportContext:
    resolved_file = Path(file_path).resolve()
    resolved_project_root = Path(project_root).resolve()

    package_root = _find_top_level_package_dir(resolved_file.parent)
    if package_root is None:
        return ModuleImportContext(
            module_name=resolved_file.stem,
            package_name="",
            sys_path_entry=str(resolved_file.parent),
            is_package=False,
        )

    import_root = package_root.parent
    try:
        relative_module = resolved_file.with_suffix("").relative_to(import_root)
    except ValueError:
        relative_module = resolved_file.with_suffix("").relative_to(resolved_project_root)
        import_root = resolved_project_root

    parts = list(relative_module.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()

    module_name = ".".join(parts)
    package_name = module_name.rpartition(".")[0]

    return ModuleImportContext(
        module_name=module_name,
        package_name=package_name,
        sys_path_entry=str(import_root),
        is_package=True,
    )