from __future__ import annotations

"""AST-based code transformer for instrumentation."""

import ast
import io
import re
import sys
import tokenize
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Pattern

from .source_map import SourceMap


@dataclass
class TransformContext:
    """Context passed to transformation hooks."""
    
    source_file: str
    original_source: str
    ast_tree: ast.AST
    source_map: SourceMap


@dataclass
class FunctionParamTarget:
    """A bound function parameter and the nodes that represent its binding slot."""

    function_node: ast.FunctionDef | ast.AsyncFunctionDef
    parameter_node: ast.arg
    binding_nodes: list[ast.AST]


class InstrumentationVisitor(ast.NodeTransformer):
    """AST visitor that instruments code with custom hooks."""
    
    def __init__(
        self,
        source_file: str,
        original_source: str = "",
        coverage_callback: str = "__runner_coverage__",
        value_callback: str = "__runner_log_value__",
        print_callback: str = "__runner_print__",
        logpoint_callback: str = "__runner_logpoint__",
        timed_log_callback: str = "__runner_log_time__",
        time_callback: str = "__runner_time__",
        enable_coverage: bool = True,
        enable_value_logging: bool = True,
        magic_comment_lines: Optional[dict[int, dict[str, bool]]] = None,
        ignore_coverage_lines: Optional[set[int]] = None,
        log_markers: Optional[list[dict[str, Any]]] = None,
    ):
        self.source_file = source_file
        self._original_source = original_source
        self._source_lines = original_source.splitlines()
        self.coverage_callback = coverage_callback
        self.value_callback = value_callback
        self.print_callback = print_callback
        self.logpoint_callback = logpoint_callback
        self.timed_log_callback = timed_log_callback
        self.time_callback = time_callback
        self.enable_coverage = enable_coverage
        self.enable_value_logging = enable_value_logging
        self._magic_comment_lines: dict[int, dict[str, bool]] = magic_comment_lines or {}
        self._ignore_coverage_lines: set[int] = ignore_coverage_lines or set()
        self._log_markers: list[dict[str, Any]] = log_markers or []
        self._injected_lines: list[tuple[int, str]] = []
        self._covered_lines: set[int] = set()  # Lines that have coverage instrumentation
        self._next_range_id: int = 0  # Sequential range ID counter
        self._line_to_range: dict[int, int] = {}  # Map from line number to range ID
        self._ranges: list[list[int]] = []  # Range arrays: [startLine, startCol, endLine, endCol]
        self._logpoint_targets: dict[int, str] = {}
        self._used_logpoints: set[str] = set()
        self._value_log_targets: dict[int, dict[str, Any]] = {}
        self._function_line_logpoint_targets: dict[int, list[str]] = {}
        self._function_param_logpoint_targets: dict[int, dict[int, list[str]]] = {}
        self._function_param_value_targets: dict[int, dict[int, dict[str, Any]]] = {}
    
    @property
    def injected_lines(self) -> list[tuple[int, str]]:
        """Lines injected during transformation: (after_line, content)."""
        return self._injected_lines
    
    @property
    def covered_lines(self) -> set[int]:
        """Original line numbers that have coverage instrumentation."""
        return self._covered_lines
    
    @property
    def line_to_range(self) -> dict[int, int]:
        """Mapping from original line numbers to range IDs."""
        return self._line_to_range
    
    @property
    def range_count(self) -> int:
        """Total number of ranges created."""
        return self._next_range_id
    
    @property
    def ranges(self) -> list[list[int]]:
        """Range arrays: each is [startLine, startCol, endLine, endCol]."""
        return self._ranges

    @property
    def used_logpoints(self) -> set[str]:
        """Logpoint IDs that were successfully instrumented."""
        return self._used_logpoints

    def plan_logpoints(self, tree: ast.AST) -> None:
        """Precompute logpoint targets from log markers."""
        if not self._log_markers:
            return

        logpoint_markers = [
            m
            for m in self._log_markers
            if m.get("logpoint") and (m.get("range") or m.get("originalRange"))
        ]
        value_markers = [
            m
            for m in self._log_markers
            if not m.get("logpoint")
            and (m.get("range") or m.get("originalRange"))
            and m.get("action") != "time"
        ]
        if not logpoint_markers and not value_markers:
            return

        # Virtual-log coverage inventory:
        # - Implemented:
        #   - General expressions in executable positions (via generic expression wrapping).
        #   - Assignment-target selections mapped to assignment RHS expressions.
        #   - FunctionDef / AsyncFunctionDef parameter bindings.
        # - TODO (intentionally unimplemented for now):
        #   - Lambda parameters: requires rewriting lambda to statements, which would
        #     materially change code shape and line mappings.
        #   - Binding-only targets (`with ... as`, `except ... as`, `for` targets,
        #     `match` captures, imports, `global`/`nonlocal`, `del` targets): there is
        #     no single intuitive "value moment" without an explicit policy.
        expr_nodes: list[ast.expr] = []
        assign_nodes: list[ast.stmt] = []
        function_nodes: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
        function_param_nodes: list[FunctionParamTarget] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.expr) and hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                expr_nodes.append(node)
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                assign_nodes.append(node)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_nodes.append(node)
                function_param_nodes.extend(self._iter_function_param_targets(node))

        for marker in logpoint_markers:
            rng = marker.get("range") or marker.get("originalRange")
            if not rng or len(rng) < 4:
                continue
            start_line, start_col, end_line, end_col = rng[:4]
            marker_id = self._marker_id(marker)

            function_node = self._find_function_definition_logpoint_target(
                function_nodes,
                start_line,
                start_col,
                end_line,
                end_col,
            )
            if function_node and marker_id is not None:
                self._function_line_logpoint_targets.setdefault(id(function_node), []).append(marker_id)
                continue

            param_target = self._find_best_function_param_target(
                function_param_nodes,
                start_line,
                start_col,
                end_line,
                end_col,
            )
            if param_target and marker_id is not None:
                by_param = self._function_param_logpoint_targets.setdefault(id(param_target.function_node), {})
                by_param.setdefault(id(param_target.parameter_node), []).append(marker_id)
                continue

            target = self._find_assignment_logpoint_target(assign_nodes, start_line, start_col, end_line, end_col)
            if not target:
                target = self._find_best_logpoint_expr(expr_nodes, start_line, start_col, end_line, end_col)
            if target and marker_id is not None:
                self._logpoint_targets[id(target)] = marker_id

        if self.enable_value_logging:
            for marker in value_markers:
                rng = marker.get("range") or marker.get("originalRange")
                if not rng or len(rng) < 4:
                    continue
                start_line, start_col, end_line, end_col = rng[:4]
                param_target = self._find_best_function_param_target(
                    function_param_nodes,
                    start_line,
                    start_col,
                    end_line,
                    end_col,
                )
                if param_target:
                    by_param = self._function_param_value_targets.setdefault(id(param_target.function_node), {})
                    by_param[id(param_target.parameter_node)] = marker
                    continue

                target = self._find_assignment_logpoint_target(assign_nodes, start_line, start_col, end_line, end_col)
                if not target:
                    target = self._find_best_logpoint_expr(expr_nodes, start_line, start_col, end_line, end_col)
                if target:
                    self._value_log_targets[id(target)] = marker
                    continue

    def _marker_id(self, marker: dict[str, Any]) -> Any:
        marker_id = marker.get("id")
        if marker_id is None:
            marker_id = marker.get("changeId")
        return marker_id

    def _iter_function_params(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.arg]:
        params: list[ast.arg] = []
        params.extend(getattr(node.args, "posonlyargs", []))
        params.extend(node.args.args)
        if node.args.vararg is not None:
            params.append(node.args.vararg)
        params.extend(node.args.kwonlyargs)
        if node.args.kwarg is not None:
            params.append(node.args.kwarg)
        return params

    def _iter_function_param_targets(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[FunctionParamTarget]:
        positional_params = [*getattr(node.args, "posonlyargs", []), *node.args.args]
        positional_defaults = list(node.args.defaults)
        positional_default_offset = len(positional_params) - len(positional_defaults)
        targets: list[FunctionParamTarget] = []

        for index, parameter in enumerate(positional_params):
            binding_nodes: list[ast.AST] = [parameter]
            default_index = index - positional_default_offset
            if default_index >= 0:
                binding_nodes.append(positional_defaults[default_index])
            targets.append(FunctionParamTarget(node, parameter, binding_nodes))

        if node.args.vararg is not None:
            targets.append(FunctionParamTarget(node, node.args.vararg, [node.args.vararg]))

        for parameter, default_value in zip(node.args.kwonlyargs, node.args.kw_defaults):
            binding_nodes = [parameter]
            if default_value is not None:
                binding_nodes.append(default_value)
            targets.append(FunctionParamTarget(node, parameter, binding_nodes))

        if node.args.kwarg is not None:
            targets.append(FunctionParamTarget(node, node.args.kwarg, [node.args.kwarg]))

        return [
            target
            for target in targets
            if all(hasattr(binding_node, "lineno") and hasattr(binding_node, "end_lineno") for binding_node in target.binding_nodes)
        ]

    def _selection_overlaps(self, node: ast.AST, start_line: int, start_col: int, end_line: int, end_col: int) -> bool:
        if not hasattr(node, "lineno") or not hasattr(node, "end_lineno"):
            return False
        node_start = (node.lineno, getattr(node, "col_offset", 0))
        node_end = (node.end_lineno, getattr(node, "end_col_offset", 0))
        selection_start = (start_line, start_col)
        selection_end = (end_line, end_col)
        return node_start <= selection_end and node_end >= selection_start

    def _find_assignment_logpoint_target(
        self,
        assign_nodes: list[ast.stmt],
        start_line: int,
        start_col: int,
        end_line: int,
        end_col: int,
    ) -> Optional[ast.expr]:
        for node in assign_nodes:
            if isinstance(node, ast.Assign):
                targets = node.targets
                value = node.value
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
                value = node.value
            elif isinstance(node, ast.AugAssign):
                targets = [node.target]
                value = node.value
            else:
                continue

            if not value:
                continue

            for target in targets:
                if self._selection_overlaps(target, start_line, start_col, end_line, end_col):
                    return value
        return None

    def _node_boundary_distance(self, node: ast.AST, start_line: int, start_col: int, end_line: int, end_col: int) -> tuple[int, int, int]:
        node_start = (node.lineno, getattr(node, "col_offset", 0))
        node_end = (node.end_lineno, getattr(node, "end_col_offset", 0))

        def dist(a: tuple[int, int], b: tuple[int, int]) -> int:
            return abs(a[0] - b[0]) * 1000 + abs(a[1] - b[1])

        boundary_delta = dist(node_start, (start_line, start_col)) + dist(node_end, (end_line, end_col))
        span_lines = node_end[0] - node_start[0]
        span_cols = (node_end[1] - node_start[1]) if span_lines == 0 else node_end[1]
        return (boundary_delta, span_lines, span_cols)

    def _find_best_logpoint_expr(
        self,
        expr_nodes: list[ast.expr],
        start_line: int,
        start_col: int,
        end_line: int,
        end_col: int,
    ) -> Optional[ast.expr]:
        candidates: list[ast.expr] = []
        for node in expr_nodes:
            if not self._can_wrap_expr(node):
                continue
            if self._selection_overlaps(node, start_line, start_col, end_line, end_col):
                candidates.append(node)

        if not candidates:
            return None

        same_line = [node for node in candidates if node.lineno == start_line]
        if same_line:
            candidates = same_line

        return min(candidates, key=lambda node: self._node_boundary_distance(node, start_line, start_col, end_line, end_col))

    def _find_best_function_param_target(
        self,
        function_param_nodes: list[FunctionParamTarget],
        start_line: int,
        start_col: int,
        end_line: int,
        end_col: int,
    ) -> Optional[FunctionParamTarget]:
        candidates = [
            target
            for target in function_param_nodes
            if any(
                self._selection_overlaps(binding_node, start_line, start_col, end_line, end_col)
                for binding_node in target.binding_nodes
            )
        ]
        if not candidates:
            return None

        same_line = [item for item in candidates if item.parameter_node.lineno == start_line]
        if same_line:
            candidates = same_line

        return min(
            candidates,
            key=lambda item: min(
                self._node_boundary_distance(binding_node, start_line, start_col, end_line, end_col)
                for binding_node in item.binding_nodes
            ),
        )

    def _find_function_definition_logpoint_target(
        self,
        function_nodes: list[ast.FunctionDef | ast.AsyncFunctionDef],
        start_line: int,
        start_col: int,
        end_line: int,
        end_col: int,
    ) -> Optional[ast.FunctionDef | ast.AsyncFunctionDef]:
        if start_line != end_line or start_col != 0 or end_col != 0:
            return None

        candidates = [
            node
            for node in function_nodes
            if node.lineno == start_line and getattr(node, "col_offset", 0) == 0 and self._iter_function_params(node)
        ]
        if not candidates:
            return None

        return min(candidates, key=lambda node: (getattr(node, "end_lineno", node.lineno), getattr(node, "end_col_offset", 0)))

    def _wrap_logpoint(self, node: ast.expr, logpoint_id: str, range_node: ast.AST) -> ast.Call:
        range_id = self._get_or_create_range_id(range_node)
        self._used_logpoints.add(logpoint_id)
        call = ast.Call(
            func=ast.Name(id=self.logpoint_callback, ctx=ast.Load()),
            args=[
                ast.Constant(value=self.source_file),
                ast.Constant(value=range_id),
                ast.Constant(value=logpoint_id),
                node,
            ],
            keywords=[],
        )
        ast.copy_location(call, node)
        ast.fix_missing_locations(call)
        return call

    def _wrap_value_log(self, node: ast.expr, marker: dict[str, Any], range_node: ast.AST) -> ast.Call:
        range_id = self._get_or_create_range_id(range_node)
        marker_id = marker.get("id")
        if marker_id is None:
            marker_id = marker.get("changeId")
        marker_trace_id = marker.get("traceId")
        marker_expression = self._marker_expression_source(marker)
        context = marker.get("context") or marker.get("exp") or marker.get("name") or marker_expression
        auto_expand = bool(marker.get("expanded"))
        keywords = [
            ast.keyword(arg="range_id", value=ast.Constant(value=range_id)),
            ast.keyword(arg="change_id", value=ast.Constant(value=marker_id)),
            ast.keyword(arg="context", value=ast.Constant(value=context)),
            ast.keyword(arg="auto_expand", value=ast.Constant(value=auto_expand)),
        ]
        if marker_trace_id is not None:
            keywords.append(ast.keyword(arg="trace_id", value=ast.Constant(value=marker_trace_id)))
            trace_eval = self._trace_eval_lambda(marker_expression, node)
            if trace_eval is not None:
                keywords.append(ast.keyword(arg="exp", value=trace_eval))
        call = ast.Call(
            func=ast.Name(id=self.value_callback, ctx=ast.Load()),
            args=[
                ast.Constant(value=self.source_file),
                ast.Constant(value=getattr(node, "lineno", getattr(range_node, "lineno", 0))),
                ast.Constant(value=context or ""),
                node,
            ],
            keywords=keywords,
        )
        ast.copy_location(call, node)
        ast.fix_missing_locations(call)
        return call

    def _marker_expression_source(self, marker: dict[str, Any]) -> Optional[str]:
        exp = marker.get("exp")
        if isinstance(exp, str) and exp.strip():
            return exp

        rng = marker.get("originalRange") or marker.get("range")
        if not isinstance(rng, list) or len(rng) < 4:
            return None

        start_line, start_col, end_line, end_col = rng[:4]
        if not all(isinstance(v, int) for v in (start_line, start_col, end_line, end_col)):
            return None
        if not self._source_lines:
            return None
        if start_line < 1 or end_line < start_line:
            return None
        if end_line > len(self._source_lines):
            return None

        lines = self._source_lines[start_line - 1:end_line]
        if not lines:
            return None

        # Keep extraction permissive; if selection is slightly off, best-effort trimming
        # preserves debugger hover behavior instead of dropping to `n/a`.
        lines[0] = lines[0][max(start_col, 0):]
        if len(lines) == 1:
            lines[0] = lines[0][:max(end_col - start_col, 0)]
        else:
            lines[-1] = lines[-1][:max(end_col, 0)]

        candidate = "\n".join(lines).strip()
        return candidate or None

    def _trace_eval_lambda(self, expression: Optional[str], node: ast.AST) -> Optional[ast.Lambda]:
        if not expression:
            return None

        try:
            parsed = ast.parse(expression, mode="eval")
            expr_node = parsed.body
        except SyntaxError:
            return None

        lambda_args = ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg="_value")],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[ast.Constant(value=None)],
        )
        lambda_node = ast.Lambda(args=lambda_args, body=expr_node)
        ast.copy_location(lambda_node, node)
        ast.fix_missing_locations(lambda_node)
        return lambda_node

    def _can_wrap_expr(self, node: ast.expr) -> bool:
        ctx = getattr(node, "ctx", None)
        if isinstance(ctx, (ast.Store, ast.Del)):
            return False
        return True

    def _apply_logpoint_or_value(self, node: ast.expr, range_node: ast.AST) -> ast.expr:
        target_id = id(node)
        logpoint_id = self._logpoint_targets.pop(target_id, None)
        if logpoint_id:
            return self._wrap_logpoint(node, logpoint_id, range_node)

        marker = self._value_log_targets.pop(target_id, None)
        if marker:
            return self._wrap_value_log(node, marker, range_node)

        return node

    def _apply_value_log(self, node: ast.expr, range_node: ast.AST) -> ast.expr:
        return self._apply_logpoint_or_value(node, range_node)

    def _is_docstring_stmt(self, node: ast.stmt) -> bool:
        return (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )

    def _is_coverage_stmt(self, node: ast.stmt) -> bool:
        return (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == self.coverage_callback
        )

    def _insert_function_param_logs(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        body: list[ast.stmt],
    ) -> list[ast.stmt]:
        function_logpoint_ids = self._function_line_logpoint_targets.pop(id(node), [])
        logpoint_map = self._function_param_logpoint_targets.pop(id(node), None)
        marker_map = self._function_param_value_targets.pop(id(node), None)
        if not function_logpoint_ids and not logpoint_map and not marker_map:
            return body

        param_logs: list[ast.stmt] = []
        for parameter in self._iter_function_params(node):
            logpoint_ids = list(function_logpoint_ids)
            if logpoint_map:
                logpoint_ids.extend(logpoint_map.get(id(parameter), []))
            marker = marker_map.get(id(parameter)) if marker_map else None
            if not logpoint_ids and not marker:
                continue

            for logpoint_id in logpoint_ids:
                # Side-effect-less: read already-bound parameter value and pass through logger.
                value_expr = ast.Name(id=parameter.arg, ctx=ast.Load())
                ast.copy_location(value_expr, parameter)
                logpoint_call = self._wrap_logpoint(value_expr, logpoint_id, node)
                logpoint_stmt = ast.Expr(value=logpoint_call)
                ast.copy_location(logpoint_stmt, parameter)
                ast.fix_missing_locations(logpoint_stmt)
                param_logs.append(logpoint_stmt)

            if marker:
                value_expr = ast.Name(id=parameter.arg, ctx=ast.Load())
                ast.copy_location(value_expr, parameter)
                log_call = self._wrap_value_log(value_expr, marker, node)
                log_stmt = ast.Expr(value=log_call)
                ast.copy_location(log_stmt, parameter)
                ast.fix_missing_locations(log_stmt)
                param_logs.append(log_stmt)

        if not param_logs:
            return body

        insert_at = 0
        if body:
            if len(body) >= 2 and self._is_coverage_stmt(body[0]) and self._is_docstring_stmt(body[1]):
                insert_at = 2
            elif self._is_docstring_stmt(body[0]):
                insert_at = 1

        return body[:insert_at] + param_logs + body[insert_at:]
    
    def _make_coverage_call(self, node: ast.stmt) -> ast.Expr:
        """Create a coverage tracking call: __runner_coverage__(file, range_id)."""
        range_id = self._create_range_id(node, register_line=True)
        
        call = ast.Call(
            func=ast.Name(id=self.coverage_callback, ctx=ast.Load()),
            args=[
                ast.Constant(value=self.source_file),
                ast.Constant(value=range_id),
            ],
            keywords=[],
        )
        expr = ast.Expr(value=call)
        ast.fix_missing_locations(expr)
        return expr

    def _create_range_id(self, node: ast.AST, *, register_line: bool = False) -> int:
        """Create a new coverage range for a node."""
        lineno = node.lineno
        col_offset = getattr(node, 'col_offset', 0)
        end_lineno = getattr(node, 'end_lineno', lineno)
        end_col_offset = getattr(node, 'end_col_offset', col_offset + 1)

        range_id = self._next_range_id
        self._next_range_id += 1
        if register_line:
            self._line_to_range.setdefault(lineno, range_id)

        # Note: Wallaby uses 1-based lines, 0-based columns
        self._ranges.append([lineno, col_offset, end_lineno, end_col_offset])
        return range_id
    
    def _make_value_log_call(self, name: str, value_node: ast.expr, lineno: int) -> ast.Expr:
        """Create a value logging call: __runner_log_value__(file, line, name, value)."""
        call = ast.Call(
            func=ast.Name(id=self.value_callback, ctx=ast.Load()),
            args=[
                ast.Constant(value=self.source_file),
                ast.Constant(value=lineno),
                ast.Constant(value=name),
                value_node,
            ],
            keywords=[
                ast.keyword(arg="range_id", value=ast.Constant(value=self._get_or_create_range_id(value_node))),
                ast.keyword(arg="context", value=ast.Constant(value=name)),
            ],
        )
        expr = ast.Expr(value=call)
        ast.copy_location(expr, value_node)
        ast.fix_missing_locations(expr)
        return expr

    def _expression_context(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id

        if hasattr(ast, "unparse"):
            try:
                return ast.unparse(node)
            except Exception:
                return ""

        return ""

    def _make_time_call(self, node: ast.AST) -> ast.Call:
        call = ast.Call(
            func=ast.Name(id=self.time_callback, ctx=ast.Load()),
            args=[],
            keywords=[],
        )
        ast.copy_location(call, node)
        ast.fix_missing_locations(call)
        return call

    def _make_timed_log_call(self, value_node: ast.expr, context: str, range_node: ast.AST) -> ast.Call:
        range_id = self._get_or_create_range_id(range_node)
        call = ast.Call(
            func=ast.Name(id=self.timed_log_callback, ctx=ast.Load()),
            args=[
                ast.Constant(value=self.source_file),
                ast.Constant(value=range_id),
                ast.Constant(value=context),
                self._make_time_call(range_node),
                value_node,
                self._make_time_call(range_node),
            ],
            keywords=[],
        )
        ast.copy_location(call, value_node)
        ast.fix_missing_locations(call)
        return call
    
    def _get_or_create_range_id(self, node: ast.AST) -> int:
        """Get existing range ID for a line or create a new one."""
        lineno = node.lineno
        if lineno in self._line_to_range:
            return self._line_to_range[lineno]

        return self._create_range_id(node, register_line=True)

    def _wrap_expr_with_coverage(self, node: ast.expr) -> ast.expr:
        """Wrap an expression so evaluating it records coverage and preserves its value."""
        range_id = self._create_range_id(node)
        coverage_call = ast.Call(
            func=ast.Name(id=self.coverage_callback, ctx=ast.Load()),
            args=[
                ast.Constant(value=self.source_file),
                ast.Constant(value=range_id),
            ],
            keywords=[],
        )
        tuple_expr = ast.Tuple(elts=[coverage_call, node], ctx=ast.Load())
        slice_node: ast.expr | ast.slice = ast.Constant(value=1)
        if sys.version_info < (3, 9):
            index_node = getattr(ast, 'Index', None)
            if index_node is not None:
                slice_node = index_node(value=slice_node)
        wrapped = ast.Subscript(value=tuple_expr, slice=slice_node, ctx=ast.Load())
        ast.copy_location(wrapped, node)
        ast.fix_missing_locations(wrapped)
        return wrapped

    def _instrument_comprehension_generators(self, generators: list[ast.comprehension]) -> list[ast.comprehension]:
        """Wrap comprehension iterables and filters with coverage-preserving expressions."""
        for generator in generators:
            generator.iter = self._wrap_expr_with_coverage(generator.iter)
            generator.ifs = [self._wrap_expr_with_coverage(condition) for condition in generator.ifs]
        return generators
    
    def _make_print_call(self, original_args: list[ast.expr], original_keywords: list[ast.keyword], node: ast.Call) -> ast.Call:
        """
        Transform print(args) into __runner_print__(file, range_id, *args, **kwargs).
        
        This allows the tracer to capture print calls with location information
        and provide expandable object trees in the value viewer.
        """
        range_id = self._get_or_create_range_id(node)
        
        # Create the new call: __runner_print__(file, range_id, *args, **kwargs)
        new_call = ast.Call(
            func=ast.Name(id=self.print_callback, ctx=ast.Load()),
            args=[
                ast.Constant(value=self.source_file),
                ast.Constant(value=range_id),
                *original_args,
            ],
            keywords=original_keywords,
        )
        ast.copy_location(new_call, node)
        ast.fix_missing_locations(new_call)
        return new_call
    
    def visit(self, node: ast.AST) -> Any:
        visited = super().visit(node)
        if isinstance(visited, ast.expr) and self._can_wrap_expr(visited):
            return self._apply_logpoint_or_value(visited, visited)
        return visited

    def visit_Call(self, node: ast.Call) -> ast.Call:
        """
        Visit call nodes. Transforms print() to __runner_print__(file, range_id, ...).
        
        This allows the tracer to capture print calls with location information
        and provide expandable object trees in the value viewer.
        """
        # Visit child nodes first
        self.generic_visit(node)
        
        # Check if this is a print() call
        if isinstance(node.func, ast.Name) and node.func.id == 'print':
            return self._make_print_call(node.args, node.keywords, node)

        return node
        
    
    def _instrument_body(
        self,
        body: list[ast.stmt],
        *,
        preserve_leading_future_block: bool = False,
    ) -> list[ast.stmt]:
        """Add coverage instrumentation to a list of statements."""
        if not self.enable_coverage:
            return body
        
        new_body = []
        future_block_end = 0
        if preserve_leading_future_block:
            scan_index = 0
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
                scan_index = 1
            while scan_index < len(body):
                stmt = body[scan_index]
                if isinstance(stmt, ast.ImportFrom) and stmt.module == "__future__":
                    scan_index += 1
                    continue
                break
            if scan_index > 0 and any(
                isinstance(stmt, ast.ImportFrom) and stmt.module == "__future__"
                for stmt in body[:scan_index]
            ):
                future_block_end = scan_index

        for index, stmt in enumerate(body):
            if hasattr(stmt, "lineno"):
                if index < future_block_end:
                    new_body.append(stmt)
                    continue
                if isinstance(stmt, ast.ImportFrom) and stmt.module == "__future__":
                    new_body.append(stmt)
                    continue
                if stmt.lineno in self._ignore_coverage_lines:
                    new_body.append(stmt)
                    continue
                coverage_call = self._make_coverage_call(stmt)
                coverage_call.lineno = stmt.lineno
                new_body.append(coverage_call)
                range_id = self._line_to_range[stmt.lineno]
                self._injected_lines.append((stmt.lineno, f"{self.coverage_callback}('{self.source_file}', {range_id})"))
                self._covered_lines.add(stmt.lineno)  # Track this line as instrumentable
            new_body.append(stmt)
        return new_body
    
    def visit_Module(self, node: ast.Module) -> ast.Module:
        """Instrument module-level statements."""
        node.body = self._instrument_body(node.body, preserve_leading_future_block=True)
        self.generic_visit(node)
        return node
    
    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        """Instrument function definitions."""
        node.body = self._instrument_body(node.body)
        node.body = self._insert_function_param_logs(node, node.body)
        self.generic_visit(node)
        return node
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        """Instrument async function definitions."""
        node.body = self._instrument_body(node.body)
        node.body = self._insert_function_param_logs(node, node.body)
        self.generic_visit(node)
        return node
    
    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        """Instrument class definitions."""
        node.body = self._instrument_body(node.body)
        self.generic_visit(node)
        return node
    
    
    def visit_Try(self, node: ast.Try) -> ast.Try:
        """Instrument try/except blocks."""
        node.body = self._instrument_body(node.body)
        node.orelse = self._instrument_body(node.orelse) if node.orelse else []
        node.finalbody = self._instrument_body(node.finalbody) if node.finalbody else []
        for handler in node.handlers:
            handler.body = self._instrument_body(handler.body)
        self.generic_visit(node)
        return node
    
    def visit_With(self, node: ast.With) -> ast.With:
        """Instrument with statements."""
        node.body = self._instrument_body(node.body)
        self.generic_visit(node)
        return node
    
    def visit_AsyncWith(self, node: ast.AsyncWith) -> ast.AsyncWith:
        """Instrument async with statements."""
        node.body = self._instrument_body(node.body)
        self.generic_visit(node)
        return node
    
    
    def visit_Match(self, node: ast.Match) -> ast.Match:
        """Instrument match statements (Python 3.10+)."""
        for case in node.cases:
            case.body = self._instrument_body(case.body)
        self.generic_visit(node)
        for case in node.cases:
            if case.guard is not None:
                case.guard = self._wrap_expr_with_coverage(case.guard)
        return node
    
    def _make_assignment_magic_print(self, node: ast.stmt, target: ast.expr) -> list[ast.stmt]:
        """If the assignment line has a magic comment, append a print call for the target."""
        if (
            self._magic_comment_lines
            and hasattr(node, "lineno")
            and node.lineno in self._magic_comment_lines
            and isinstance(target, ast.Name)
        ):
            magic_flags = self._magic_comment_lines.get(node.lineno, {})
            if magic_flags.get("measure_time") and isinstance(getattr(node, "value", None), ast.expr):
                node.value = self._make_timed_log_call(getattr(node, "value"), target.id, node)
                return [node]
            range_id = self._get_or_create_range_id(node)
            auto_expand = magic_flags.get('auto_expand', False)
            call = ast.Call(
                func=ast.Name(id=self.print_callback, ctx=ast.Load()),
                args=[
                    ast.Constant(value=self.source_file),
                    ast.Constant(value=range_id),
                    ast.Name(id=target.id, ctx=ast.Load()),
                ],
                keywords=[
                    ast.keyword(arg="auto_expand", value=ast.Constant(value=auto_expand)),
                ] if auto_expand else [],
            )
            print_stmt = ast.Expr(value=call)
            ast.copy_location(print_stmt, node)
            ast.fix_missing_locations(print_stmt)
            return [node, print_stmt]
        return [node]

    def visit_Assign(self, node: ast.Assign) -> ast.Assign | list[ast.stmt]:
        """Visit assignment statements, with magic comment support."""
        self.generic_visit(node)
        target = node.targets[0] if len(node.targets) == 1 else None
        result = self._make_assignment_magic_print(node, target)
        return result if len(result) > 1 else node

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AnnAssign | list[ast.stmt]:
        """Visit annotated assignments, with magic comment support."""
        self.generic_visit(node)
        result = self._make_assignment_magic_print(node, node.target)
        return result if len(result) > 1 else node

    def visit_AugAssign(self, node: ast.AugAssign) -> ast.AugAssign | list[ast.stmt]:
        """Visit augmented assignments, with magic comment support."""
        self.generic_visit(node)
        result = self._make_assignment_magic_print(node, node.target)
        return result if len(result) > 1 else node

    def visit_Expr(self, node: ast.Expr) -> ast.Expr:
        """Handle magic comment and bare identifier auto-log for expression statements."""
        self.generic_visit(node)

        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            if node.value.func.id in {
                self.coverage_callback,
                self.value_callback,
                self.print_callback,
                self.logpoint_callback,
            }:
                return node

        if hasattr(node, "lineno") and node.lineno in self._magic_comment_lines:
            magic_flags = self._magic_comment_lines.get(node.lineno, {})
            if magic_flags.get("measure_time"):
                timed_call = self._make_timed_log_call(node.value, self._expression_context(node.value), node)
                new_node = ast.Expr(value=timed_call)
                ast.copy_location(new_node, node)
                ast.fix_missing_locations(new_node)
                return new_node
            range_id = self._get_or_create_range_id(node)
            auto_expand = magic_flags.get('auto_expand', False)

            call = ast.Call(
                func=ast.Name(id=self.print_callback, ctx=ast.Load()),
                args=[
                    ast.Constant(value=self.source_file),
                    ast.Constant(value=range_id),
                    node.value,
                ],
                keywords=[
                    ast.keyword(arg="auto_expand", value=ast.Constant(value=auto_expand)),
                ] if auto_expand else [],
            )

            new_node = ast.Expr(value=call)
            ast.copy_location(new_node, node)
            ast.fix_missing_locations(new_node)
            return new_node

        if isinstance(node.value, ast.Name) and isinstance(node.value.ctx, ast.Load):
            return self._make_value_log_call(node.value.id, node.value, node.lineno)

        return node

    def visit_Return(self, node: ast.Return) -> ast.Return:
        """Visit return statements, with magic comment support."""
        self.generic_visit(node)

        if (
            self._magic_comment_lines
            and node.value is not None
            and hasattr(node, "lineno")
            and node.lineno in self._magic_comment_lines
        ):
            magic_flags = self._magic_comment_lines.get(node.lineno, {})
            if magic_flags.get("measure_time"):
                node.value = self._make_timed_log_call(node.value, self._expression_context(node.value), node)
                return node
            range_id = self._get_or_create_range_id(node)
            auto_expand = magic_flags.get('auto_expand', False)
            call = ast.Call(
                func=ast.Name(id=self.print_callback, ctx=ast.Load()),
                args=[
                    ast.Constant(value=self.source_file),
                    ast.Constant(value=range_id),
                    node.value,
                ],
                keywords=[
                    ast.keyword(arg="auto_expand", value=ast.Constant(value=auto_expand)),
                ] if auto_expand else [],
            )
            ast.copy_location(call, node)
            ast.fix_missing_locations(call)
            node.value = call

        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.BoolOp:
        """Instrument boolean operands so short-circuit coverage can be partial."""
        self.generic_visit(node)
        node.values = [self._wrap_expr_with_coverage(value) for value in node.values]
        return node

    def visit_ListComp(self, node: ast.ListComp) -> ast.ListComp:
        """Instrument list comprehensions so filters and elements can be partially covered."""
        self.generic_visit(node)
        node.elt = self._wrap_expr_with_coverage(node.elt)
        node.generators = self._instrument_comprehension_generators(node.generators)
        return node

    def visit_SetComp(self, node: ast.SetComp) -> ast.SetComp:
        """Instrument set comprehensions so filters and elements can be partially covered."""
        self.generic_visit(node)
        node.elt = self._wrap_expr_with_coverage(node.elt)
        node.generators = self._instrument_comprehension_generators(node.generators)
        return node

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> ast.GeneratorExp:
        """Instrument generator expressions so filters and yielded values can be partially covered."""
        self.generic_visit(node)
        node.elt = self._wrap_expr_with_coverage(node.elt)
        node.generators = self._instrument_comprehension_generators(node.generators)
        return node

    def visit_DictComp(self, node: ast.DictComp) -> ast.DictComp:
        """Instrument dict comprehensions so filters, keys, and values can be partially covered."""
        self.generic_visit(node)
        node.key = self._wrap_expr_with_coverage(node.key)
        node.value = self._wrap_expr_with_coverage(node.value)
        node.generators = self._instrument_comprehension_generators(node.generators)
        return node

    def visit_IfExp(self, node: ast.IfExp) -> ast.IfExp:
        """Instrument ternary expressions so only executed branches are covered."""
        self.generic_visit(node)
        node.test = self._wrap_expr_with_coverage(node.test)
        node.body = self._wrap_expr_with_coverage(node.body)
        node.orelse = self._wrap_expr_with_coverage(node.orelse)
        return node

    def visit_Compare(self, node: ast.Compare) -> ast.Compare:
        """Instrument chained comparisons so later operands can remain uncovered."""
        self.generic_visit(node)
        if len(node.comparators) > 1:
            node.comparators = [self._wrap_expr_with_coverage(comparator) for comparator in node.comparators]
        return node

    def visit_Assert(self, node: ast.Assert) -> ast.Assert:
        """Instrument assert messages so passing asserts can remain partially covered."""
        self.generic_visit(node)
        if node.msg is not None:
            node.msg = self._wrap_expr_with_coverage(node.msg)
        return node

    def visit_If(self, node: ast.If) -> ast.If:
        """Instrument if statements."""
        node.body = self._instrument_body(node.body)
        node.orelse = self._instrument_body(node.orelse) if node.orelse else []
        self.generic_visit(node)
        return node

    def visit_While(self, node: ast.While) -> ast.While:
        """Instrument while loops."""
        node.body = self._instrument_body(node.body)
        node.orelse = self._instrument_body(node.orelse) if node.orelse else []
        self.generic_visit(node)
        return node

    def _prepend_for_magic_print(self, node: ast.For | ast.AsyncFor) -> None:
        """If a for loop line has a magic comment and a Name target, prepend a print call to the body."""
        if (
            self._magic_comment_lines
            and hasattr(node, "lineno")
            and node.lineno in self._magic_comment_lines
            and isinstance(node.target, ast.Name)
        ):
            magic_flags = self._magic_comment_lines.get(node.lineno, {})
            if magic_flags.get("measure_time"):
                node.iter = self._make_timed_log_call(node.iter, self._expression_context(node.iter), node)
                return
            range_id = self._get_or_create_range_id(node)
            auto_expand = magic_flags.get('auto_expand', False)
            call = ast.Call(
                func=ast.Name(id=self.print_callback, ctx=ast.Load()),
                args=[
                    ast.Constant(value=self.source_file),
                    ast.Constant(value=range_id),
                    ast.Name(id=node.target.id, ctx=ast.Load()),
                ],
                keywords=[
                    ast.keyword(arg="auto_expand", value=ast.Constant(value=auto_expand)),
                ] if auto_expand else [],
            )
            print_stmt = ast.Expr(value=call)
            ast.copy_location(print_stmt, node)
            ast.fix_missing_locations(print_stmt)
            node.body.insert(0, print_stmt)

    def visit_For(self, node: ast.For) -> ast.For:
        """Instrument for loops, with magic comment support."""
        node.body = self._instrument_body(node.body)
        node.orelse = self._instrument_body(node.orelse) if node.orelse else []
        self._prepend_for_magic_print(node)
        self.generic_visit(node)
        return node

    def visit_AsyncFor(self, node: ast.AsyncFor) -> ast.AsyncFor:
        """Instrument async for loops, with magic comment support."""
        node.body = self._instrument_body(node.body)
        node.orelse = self._instrument_body(node.orelse) if node.orelse else []
        self._prepend_for_magic_print(node)
        self.generic_visit(node)
        return node


@dataclass
class CodeTransformer:
    """Transforms Python source code with instrumentation."""
    
    enable_coverage: bool = True
    enable_value_logging: bool = True
    rewrite_asserts: bool = False
    coverage_callback: str = "__runner_coverage__"
    value_callback: str = "__runner_log_value__"
    print_callback: str = "__runner_print__"
    logpoint_callback: str = "__runner_logpoint__"
    timed_log_callback: str = "__runner_log_time__"
    time_callback: str = "__runner_time__"
    ignore_coverage: Optional[object] = None
    ignore_coverage_for_file: Optional[object] = None
    custom_transforms: list[Callable[[TransformContext], ast.AST]] = field(default_factory=list)
    _ignore_coverage_regex: Optional[Pattern[str]] = field(default=None, init=False)
    _ignore_file_coverage_regex: Optional[Pattern[str]] = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._ignore_coverage_regex = self._compile_hint_regex(self.ignore_coverage)
        self._ignore_file_coverage_regex = self._compile_hint_regex(self.ignore_coverage_for_file)
    
    def add_transform(self, transform: Callable[[TransformContext], ast.AST]) -> None:
        """Add a custom AST transformation."""
        self.custom_transforms.append(transform)

    def _prepare_log_markers(
        self,
        source: str,
        log_markers: Optional[list[dict[str, Any]]],
    ) -> Optional[list[dict[str, Any]]]:
        if not log_markers:
            return log_markers

        lines = source.splitlines()
        prepared: list[dict[str, Any]] = []

        def _extract_range(rng: list[int]) -> str:
            if len(rng) < 4:
                return ""
            start_line, start_col, end_line, end_col = rng[:4]
            if start_line <= 0 or end_line <= 0:
                return ""
            if start_line == end_line:
                line = lines[start_line - 1] if start_line - 1 < len(lines) else ""
                return line[start_col:end_col]
            parts = []
            first = lines[start_line - 1] if start_line - 1 < len(lines) else ""
            parts.append(first[start_col:])
            for line_no in range(start_line, end_line - 1):
                if 0 <= line_no - 1 < len(lines):
                    parts.append(lines[line_no - 1])
            last = lines[end_line - 1] if end_line - 1 < len(lines) else ""
            parts.append(last[:end_col])
            return "\n".join(parts)

        for marker in log_markers:
            cloned = dict(marker)
            if not cloned.get("context") and not cloned.get("exp"):
                rng = cloned.get("range") or cloned.get("originalRange")
                if rng and isinstance(rng, (list, tuple)):
                    extracted = _extract_range(list(rng))
                    if extracted:
                        context = " ".join(extracted.split())
                        if context:
                            cloned["context"] = context
            prepared.append(cloned)

        return prepared

    def _normalize_node_ranges(self, tree: ast.AST) -> None:
        """
        Ensure location metadata is monotonic so compile() accepts rewritten ASTs.

        Some rewritten nodes inherit a starting location from the original node
        while ast.fix_missing_locations populates child end positions from nested
        generated nodes. On Python 3.11+ this can surface as:
        "AST node line range (X, Y) is not valid".
        """
        for node in ast.walk(tree):
            lineno = getattr(node, "lineno", None)
            end_lineno = getattr(node, "end_lineno", None)
            if lineno is None or end_lineno is None:
                continue

            if end_lineno < lineno:
                node.end_lineno = lineno
                end_lineno = lineno

            col_offset = getattr(node, "col_offset", None)
            end_col_offset = getattr(node, "end_col_offset", None)
            if col_offset is None or end_col_offset is None:
                continue

            if end_lineno == lineno and end_col_offset < col_offset:
                node.end_col_offset = col_offset

    def _to_source(self, tree: ast.AST, fallback_source: str) -> str:
        """Return Python source for an AST when available, else a safe fallback."""
        if hasattr(ast, "unparse"):
            return ast.unparse(tree)
        return fallback_source

    def transform(
        self,
        source: str,
        source_file: str,
        log_markers: Optional[list[dict[str, Any]]] = None,
    ) -> tuple[str, SourceMap]:
        """
        Transform source code with instrumentation.
        Returns (transformed_source, source_map).
        """
        magic_comment_lines = self._get_magic_comment_lines(source)
        ignore_file, ignore_inline, ignore_standalone = self._get_ignore_coverage_hints(source)
        log_markers = self._prepare_log_markers(source, log_markers)

        # Parse the original source
        tree = ast.parse(source, filename=source_file)

        ignore_coverage_lines: set[int] = set()
        enable_coverage = self.enable_coverage
        if ignore_file:
            enable_coverage = False
        elif ignore_inline or ignore_standalone:
            ignore_coverage_lines = self._resolve_ignore_coverage_lines(tree, ignore_inline, ignore_standalone)
        
        # Create source map
        source_map = SourceMap(source_file=source_file, original_source=source)
        
        # Apply instrumentation visitor
        visitor = InstrumentationVisitor(
            source_file=source_file,
            original_source=source,
            coverage_callback=self.coverage_callback,
            value_callback=self.value_callback,
            print_callback=self.print_callback,
            logpoint_callback=self.logpoint_callback,
            timed_log_callback=self.timed_log_callback,
            time_callback=self.time_callback,
            enable_coverage=enable_coverage,
            enable_value_logging=self.enable_value_logging,
            magic_comment_lines=magic_comment_lines,
            ignore_coverage_lines=ignore_coverage_lines,
            log_markers=log_markers,
        )
        visitor.plan_logpoints(tree)
        tree = visitor.visit(tree)
        ast.fix_missing_locations(tree)
        self._normalize_node_ranges(tree)
        
        # Store covered lines and range mappings in source map
        source_map.covered_lines = visitor.covered_lines
        source_map.line_to_range = visitor.line_to_range
        source_map.range_count = visitor.range_count
        source_map.ranges = visitor.ranges
        source_map.used_logpoints = visitor.used_logpoints
        
        # Apply custom transforms
        context = TransformContext(
            source_file=source_file,
            original_source=source,
            ast_tree=tree,
            source_map=source_map,
        )
        for transform in self.custom_transforms:
            tree = transform(context)
            ast.fix_missing_locations(tree)
        
        # Generate transformed source
        transformed = self._to_source(tree, source)
        
        # Build source map by comparing lines
        self._build_source_map(source, transformed, source_map, visitor.injected_lines)

        return transformed, source_map

    def _get_magic_comment_lines(self, source: str) -> dict[int, dict[str, bool]]:
        """Detect lines with magic auto-log comments such as # ?, # ?+, # ?., # ?.+ and # ?+."""
        magic_lines: dict[int, dict[str, bool]] = {}
        try:
            for token in tokenize.generate_tokens(io.StringIO(source).readline):
                if token.type != tokenize.COMMENT:
                    continue
                match = re.search(r"#\s*\?\s*([.+\s]*)$", token.string)
                if not match:
                    continue
                suffix = "".join(match.group(1).split())
                if suffix not in {"", "+", ".", ".+", "+."}:
                    continue
                flags: dict[str, bool] = {}
                if "+" in suffix:
                    flags["auto_expand"] = True
                if "." in suffix:
                    flags["measure_time"] = True
                magic_lines[token.start[0]] = flags
        except tokenize.TokenError:
            return {}
        return magic_lines

    def _compile_hint_regex(self, value: Optional[object]) -> Optional[Pattern[str]]:
        if value is None:
            return None
        if isinstance(value, re.Pattern):
            return value
        if not isinstance(value, str):
            return None
        pattern = value
        flags = 0
        if pattern.startswith("__REGEXP "):
            raw = pattern[len("__REGEXP "):]
            if raw.startswith("/") and raw.count("/") >= 2:
                last_slash = raw.rfind("/")
                pattern = raw[1:last_slash]
                flag_str = raw[last_slash + 1:]
                if "i" in flag_str:
                    flags |= re.IGNORECASE
                if "m" in flag_str:
                    flags |= re.MULTILINE
                if "s" in flag_str:
                    flags |= re.DOTALL
            else:
                pattern = raw
        try:
            return re.compile(pattern, flags)
        except re.error:
            return None

    def _get_ignore_coverage_hints(self, source: str) -> tuple[bool, set[int], set[int]]:
        """Detect ignore coverage hints from comments."""
        if not self._ignore_coverage_regex and not self._ignore_file_coverage_regex:
            return False, set(), set()

        ignore_file = False
        inline_lines: set[int] = set()
        standalone_lines: set[int] = set()
        lines = source.splitlines()

        try:
            for token in tokenize.generate_tokens(io.StringIO(source).readline):
                if token.type != tokenize.COMMENT:
                    continue
                comment_text = token.string
                if self._ignore_file_coverage_regex and self._ignore_file_coverage_regex.search(comment_text):
                    ignore_file = True
                if self._ignore_coverage_regex and self._ignore_coverage_regex.search(comment_text):
                    line_no = token.start[0]
                    line_text = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
                    prefix = line_text[: token.start[1]]
                    if prefix.strip():
                        inline_lines.add(line_no)
                    else:
                        standalone_lines.add(line_no)
        except tokenize.TokenError:
            return False, set(), set()

        return ignore_file, inline_lines, standalone_lines

    def _resolve_ignore_coverage_lines(
        self,
        tree: ast.AST,
        inline_lines: set[int],
        standalone_lines: set[int],
    ) -> set[int]:
        statements = [node for node in ast.walk(tree) if isinstance(node, ast.stmt) and hasattr(node, "lineno")]
        statements_sorted = sorted(
            statements,
            key=lambda node: (node.lineno, getattr(node, "col_offset", 0)),
        )
        by_line: dict[int, list[ast.stmt]] = {}
        for stmt in statements_sorted:
            by_line.setdefault(stmt.lineno, []).append(stmt)

        targets: list[ast.stmt] = []
        for line in inline_lines:
            if line in by_line:
                targets.append(by_line[line][0])

        if standalone_lines:
            for line in sorted(standalone_lines):
                for stmt in statements_sorted:
                    if stmt.lineno > line:
                        targets.append(stmt)
                        break

        ignore_lines: set[int] = set()
        for target in targets:
            for node in ast.walk(target):
                if isinstance(node, ast.stmt) and hasattr(node, "lineno"):
                    ignore_lines.add(node.lineno)

        return ignore_lines
    
    def _build_source_map(
        self,
        original: str,
        transformed: str,
        source_map: SourceMap,
        injected: list[tuple[int, str]],
    ) -> None:
        """Build source map from original and transformed source."""
        original_lines = original.splitlines()
        transformed_lines = transformed.splitlines()

        # Build helpers to map injected lines to original lines
        range_id_to_line: dict[int, int] = {}
        for line_no, range_id in source_map.line_to_range.items():
            range_id_to_line[range_id] = line_no

        def _parse_int_arg(line: str, callback: str) -> Optional[int]:
            try:
                # Expect: callback('file', <int> ...) or callback("file", <int> ...)
                start = line.index(callback) + len(callback)
                open_paren = line.index("(", start)
                comma = line.index(",", open_paren + 1)
                rest = line[comma + 1 :]
                # First arg after the comma should be an int
                number = ""
                for ch in rest.strip():
                    if ch.isdigit():
                        number += ch
                    else:
                        break
                return int(number) if number else None
            except Exception:
                return None

        original_idx = 0  # 0-based index into original_lines
        for trans_line in transformed_lines:
            stripped = trans_line.strip()

            # Map injected coverage/value-log lines to their original line
            if self.coverage_callback in trans_line:
                range_id = _parse_int_arg(trans_line, self.coverage_callback)
                if range_id is not None and range_id in range_id_to_line:
                    orig_line = range_id_to_line[range_id]
                else:
                    orig_line = min(original_idx + 1, len(original_lines)) or 1
                source_map.inject_line(orig_line, trans_line)
                continue

            if self.value_callback in trans_line:
                line_no = _parse_int_arg(trans_line, self.value_callback)
                orig_line = line_no if line_no is not None else (min(original_idx + 1, len(original_lines)) or 1)
                source_map.inject_line(orig_line, trans_line)
                continue

            # For non-injected lines, try to align by content to skip blank lines/comments
            if stripped == "":
                # Map blank line to the next blank original line, if any
                match_idx = None
                for i in range(original_idx, len(original_lines)):
                    if original_lines[i].strip() == "":
                        match_idx = i
                        break
                if match_idx is None:
                    match_idx = min(original_idx, len(original_lines) - 1)
                orig_line = match_idx + 1 if original_lines else 1
                source_map.add_original_line(orig_line, trans_line)
                original_idx = match_idx + 1
                continue

            match_idx = None
            for i in range(original_idx, len(original_lines)):
                if original_lines[i].strip() == stripped:
                    match_idx = i
                    break
            if match_idx is None:
                # Fallback to sequential mapping
                original_idx = min(original_idx + 1, len(original_lines))
                orig_line = original_idx if original_idx > 0 else 1
                source_map.add_original_line(orig_line, trans_line)
            else:
                orig_line = match_idx + 1
                source_map.add_original_line(orig_line, trans_line)
                original_idx = match_idx + 1

        source_map.finalize()
    
    def transform_for_exec(
        self,
        source: str,
        source_file: str,
        log_markers: Optional[list[dict[str, Any]]] = None,
    ) -> tuple[object, str, SourceMap]:
        """
        Transform source for execution.
        Returns (compiled_code, transformed_source, source_map).

        We compile from the AST directly so traceback line numbers match
        original source locations (instrumented nodes keep original lineno).
        """
        magic_comment_lines = self._get_magic_comment_lines(source)
        ignore_file, ignore_inline, ignore_standalone = self._get_ignore_coverage_hints(source)
        log_markers = self._prepare_log_markers(source, log_markers)

        # Parse the original source
        tree = ast.parse(source, filename=source_file)

        ignore_coverage_lines: set[int] = set()
        enable_coverage = self.enable_coverage
        if ignore_file:
            enable_coverage = False
        elif ignore_inline or ignore_standalone:
            ignore_coverage_lines = self._resolve_ignore_coverage_lines(tree, ignore_inline, ignore_standalone)

        # Create source map (identity for traceback translation)
        source_map = SourceMap(source_file=source_file, original_source=source)

        # Apply instrumentation visitor
        visitor = InstrumentationVisitor(
            source_file=source_file,
            original_source=source,
            coverage_callback=self.coverage_callback,
            value_callback=self.value_callback,
            print_callback=self.print_callback,
            logpoint_callback=self.logpoint_callback,
            timed_log_callback=self.timed_log_callback,
            time_callback=self.time_callback,
            enable_coverage=enable_coverage,
            enable_value_logging=self.enable_value_logging,
            magic_comment_lines=magic_comment_lines,
            ignore_coverage_lines=ignore_coverage_lines,
            log_markers=log_markers,
        )
        visitor.plan_logpoints(tree)
        tree = visitor.visit(tree)
        ast.fix_missing_locations(tree)
        self._normalize_node_ranges(tree)

        # Store covered lines and range mappings in source map
        source_map.covered_lines = visitor.covered_lines
        source_map.line_to_range = visitor.line_to_range
        source_map.range_count = visitor.range_count
        source_map.ranges = visitor.ranges
        source_map.used_logpoints = visitor.used_logpoints

        # Apply custom transforms
        context = TransformContext(
            source_file=source_file,
            original_source=source,
            ast_tree=tree,
            source_map=source_map,
        )
        for transform in self.custom_transforms:
            tree = transform(context)
            ast.fix_missing_locations(tree)
            self._normalize_node_ranges(tree)

        # Generate transformed source for diagnostics / get_source.
        # This must happen BEFORE pytest assertion rewriting because rewrite_asserts
        # injects synthetic AST identifiers (e.g. @py_builtins, @pytest_ar) that
        # are valid only as AST nodes and cannot be serialised back to text.
        transformed = self._to_source(tree, source)
        source_map.transformed_source = transformed

        # Apply pytest assertion rewriting after instrumentation so that
        # assert statements produce detailed error messages with actual/expected
        # values (e.g. "assert 4 == 3" instead of just "AssertionError").
        # Applied after instrumentation to avoid creating extra coverage ranges
        # for the expanded assert statements.
        if self.rewrite_asserts:
            try:
                from _pytest.assertion.rewrite import rewrite_asserts as _rewrite_asserts
                _rewrite_asserts(tree, source.encode())
                ast.fix_missing_locations(tree)
            except Exception:
                pass  # pytest not available or rewrite failed; continue without

        # Compile from AST so line numbers align with original source when possible.
        try:
            compiled = compile(tree, source_file, "exec")
        except ValueError as error:
            if "AST node line range" not in str(error):
                raise
            # Some generated location metadata combinations are rejected by newer
            # Python compilers even after fix_missing_locations(). Reparse the
            # transformed source to recover a compiler-valid tree while preserving
            # the instrumented semantics. Note: `transformed` is the pre-rewrite_asserts
            # text so it is always valid Python.
            compiled = compile(transformed, source_file, "exec")

        return compiled, transformed, source_map
