"""Static, single-file Python analysis built on the standard AST module."""

from dataclasses import dataclass
import ast


@dataclass(frozen=True)
class FunctionInfo:
    qualified_name: str
    name: str
    line: int
    end_line: int
    docstring: str | None


@dataclass(frozen=True)
class CallInfo:
    caller: str
    name: str
    line: int
    dynamic: bool = False


@dataclass(frozen=True)
class ImportInfo:
    module: str
    name: str | None
    alias: str
    line: int
    relative_level: int = 0


@dataclass(frozen=True)
class ParseResult:
    functions: list[FunctionInfo]
    calls: list[CallInfo]
    imports: list[ImportInfo]


def _attribute_name(node: ast.AST) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


class _FunctionCallVisitor(ast.NodeVisitor):
    def __init__(self, caller: str):
        self.caller = caller
        self.calls: list[CallInfo] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = node.func.id if isinstance(node.func, ast.Name) else _attribute_name(node.func)
        dynamic = name is None
        self.calls.append(CallInfo(self.caller, name or "unknown/dynamic", node.lineno, dynamic))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.generic_visit(node)


class _Parser(ast.NodeVisitor):
    def __init__(self) -> None:
        self.functions: list[FunctionInfo] = []
        self.calls: list[CallInfo] = []
        self.imports: list[ImportInfo] = []
        self.scope: list[str] = []

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualified_name = ".".join([*self.scope, node.name])
        self.functions.append(
            FunctionInfo(
                qualified_name=qualified_name,
                name=node.name,
                line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                docstring=ast.get_docstring(node),
            )
        )
        visitor = _FunctionCallVisitor(qualified_name)
        for statement in node.body:
            visitor.visit(statement)
        self.calls.extend(visitor.calls)
        self.scope.append(node.name)
        for statement in node.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.visit(statement)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        for statement in node.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.visit(statement)
        self.scope.pop()

    def visit_Import(self, node: ast.Import) -> None:
        for imported in node.names:
            self.imports.append(ImportInfo(imported.name, None, imported.asname or imported.name.split(".")[0], node.lineno))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for imported in node.names:
            self.imports.append(ImportInfo(module, imported.name, imported.asname or imported.name, node.lineno, node.level))


def parse_file(source_code: str) -> ParseResult:
    """Parse Python source into functions, calls, and imports with line evidence."""
    parser = _Parser()
    parser.visit(ast.parse(source_code))
    return ParseResult(parser.functions, parser.calls, parser.imports)