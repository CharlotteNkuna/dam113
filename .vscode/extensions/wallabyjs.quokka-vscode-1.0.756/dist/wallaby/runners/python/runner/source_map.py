from __future__ import annotations

"""Source mapping for tracking line number transformations."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LineMapping:
    """Maps a line in transformed code back to original source."""
    
    original_line: int
    transformed_line: int
    original_column: int = 0
    transformed_column: int = 0
    source_file: str = ""
    # Content added by transformation (None if line existed in original)
    injected_content: Optional[str] = None
    
    @property
    def is_injected(self) -> bool:
        """Returns True if this line was added by transformation."""
        return self.injected_content is not None


@dataclass
class SourceMap:
    """Tracks mappings between original and transformed source code."""
    
    source_file: str
    original_source: str
    transformed_source: str = ""
    mappings: list[LineMapping] = field(default_factory=list)
    covered_lines: set[int] = field(default_factory=set)  # Lines with coverage instrumentation
    line_to_range: dict[int, int] = field(default_factory=dict)  # Map from line number to range ID
    range_count: int = 0  # Total number of coverage ranges
    ranges: list[list[int]] = field(default_factory=list)  # Range arrays: [startLine, startCol, endLine, endCol]
    
    def __post_init__(self):
        self._original_lines = self.original_source.splitlines()
        self._transformed_lines: list[str] = []
        self._current_original_line = 1
        self._current_transformed_line = 1
    
    def add_original_line(self, original_line_num: int, content: str) -> int:
        """Add a line from original source, returns transformed line number."""
        transformed_line = self._current_transformed_line
        self.mappings.append(LineMapping(
            original_line=original_line_num,
            transformed_line=transformed_line,
            source_file=self.source_file,
        ))
        self._transformed_lines.append(content)
        self._current_transformed_line += 1
        return transformed_line
    
    def inject_line(self, after_original_line: int, content: str) -> int:
        """Inject a new line (instrumentation), returns transformed line number."""
        transformed_line = self._current_transformed_line
        self.mappings.append(LineMapping(
            original_line=after_original_line,
            transformed_line=transformed_line,
            source_file=self.source_file,
            injected_content=content,
        ))
        self._transformed_lines.append(content)
        self._current_transformed_line += 1
        return transformed_line
    
    def get_original_location(self, transformed_line: int) -> Optional[tuple[int, bool]]:
        """
        Get original line number for a transformed line.
        Returns (original_line, is_injected) or None if not found.
        """
        for mapping in self.mappings:
            if mapping.transformed_line == transformed_line:
                return (mapping.original_line, mapping.is_injected)
        return None
    
    def get_transformed_location(self, original_line: int) -> Optional[int]:
        """Get the transformed line number for an original line."""
        for mapping in self.mappings:
            if mapping.original_line == original_line and not mapping.is_injected:
                return mapping.transformed_line
        return None
    
    def finalize(self) -> str:
        """Finalize and return the transformed source."""
        self.transformed_source = "\n".join(self._transformed_lines)
        return self.transformed_source
    
    @property
    def transformed_line_count(self) -> int:
        """Get the number of lines in the transformed source."""
        if self.transformed_source:
            return len(self.transformed_source.splitlines())
        return len(self._transformed_lines)
    
    @property
    def original_line_count(self) -> int:
        """Get the number of lines in the original source."""
        return len(self._original_lines)
    
    def translate_traceback_line(self, transformed_line: int) -> int:
        """Translate a traceback line number back to original source."""
        result = self.get_original_location(transformed_line)
        if result:
            return result[0]
        return transformed_line
    
    def to_dict(self) -> dict:
        """Serialize source map to dictionary."""
        return {
            "source_file": self.source_file,
            "mappings": [
                {
                    "original": m.original_line,
                    "transformed": m.transformed_line,
                    "injected": m.is_injected,
                }
                for m in self.mappings
            ],
        }
    
    @classmethod
    def from_dict(cls, data: dict, original_source: str, transformed_source: str) -> "SourceMap":
        """Deserialize source map from dictionary."""
        source_map = cls(
            source_file=data["source_file"],
            original_source=original_source,
            transformed_source=transformed_source,
        )
        for m in data["mappings"]:
            source_map.mappings.append(LineMapping(
                original_line=m["original"],
                transformed_line=m["transformed"],
                source_file=data["source_file"],
                injected_content="<injected>" if m["injected"] else None,
            ))
        return source_map
