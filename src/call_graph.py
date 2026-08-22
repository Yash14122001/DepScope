"""Cross-file call graph construction using parsed Python source metadata."""

from dataclasses import dataclass
from pathlib import PurePosixPath

from .code_parser import FunctionInfo, ImportInfo, ParseResult


UNKNOWN_DYNAMIC = "unknown/dynamic"


@dataclass(frozen=True)
class CallEdge:
    caller: str
    callee: str
    line: int
    dynamic: bool = False


class CallGraph:
    def __init__(self, results: dict[str, ParseResult]):
        self.results = results
        self.functions: dict[str, FunctionInfo] = {}
        self.edges: list[CallEdge] = []
        self._build()

    def _build(self) -> None:
        module_functions: dict[str, dict[str, str]] = {}
        for path, result in self.results.items():
            for function in result.functions:
                node = f"{path}::{function.qualified_name}"
                self.functions[node] = function
                module_functions.setdefault(_module_name(path), {})[function.qualified_name] = node

        for path, result in self.results.items():
            imports = _import_bindings(path, result.imports, module_functions)
            own_functions = module_functions.get(_module_name(path), {})
            class_names = {function.qualified_name.rsplit(".", 1)[0] for function in result.functions if "." in function.qualified_name}
            for call in result.calls:
                caller = f"{path}::{call.caller}"
                if call.dynamic:
                    self.edges.append(CallEdge(caller, UNKNOWN_DYNAMIC, call.line, True))
                    continue
                target = _resolve_call(call.name, call.caller, own_functions, imports, module_functions, class_names)
                if target:
                    self.edges.append(CallEdge(caller, target, call.line))

    def find_callers(self, function_name: str) -> list[CallEdge]:
        """Return edges whose callee matches an exact node, qualified, or simple name."""
        targets = _matching_nodes(function_name, self.functions)
        return [edge for edge in self.edges if edge.callee in targets]

    def find_callees(self, function_name: str) -> list[CallEdge]:
        """Return resolved and dynamic calls made by a matching function."""
        callers = _matching_nodes(function_name, self.functions)
        return [edge for edge in self.edges if edge.caller in callers]


def _module_name(path: str) -> str:
    parsed = PurePosixPath(path.replace("\\", "/"))
    parts = list(parsed.parts)
    if parsed.name == "__init__.py":
        parts = parts[:-1]
    elif parsed.suffix == ".py":
        parts[-1] = parsed.stem
    return ".".join(parts)


def _import_bindings(path: str, imports: list[ImportInfo], modules: dict[str, dict[str, str]]) -> dict[str, str]:
    bindings: dict[str, str] = {}
    current_parts = _module_name(path).split(".")
    for imported in imports:
        module_parts = current_parts[:-1] if imported.relative_level else []
        module_parts = module_parts[: max(0, len(module_parts) - imported.relative_level + 1)]
        module = ".".join([*module_parts, imported.module]).strip(".")
        if imported.name:
            target = modules.get(module, {}).get(imported.name)
            if target:
                bindings[imported.alias] = target
        elif module in modules:
            bindings[imported.alias] = module
    return bindings


def _resolve_call(
    name: str,
    caller: str,
    own: dict[str, str],
    imports: dict[str, str],
    modules: dict[str, dict[str, str]],
    classes: set[str],
) -> str | None:
    if name in own:
        return own[name]
    if "." not in name and name in imports:
        return imports[name]
    if "." in name:
        prefix, remainder = name.split(".", 1)
        imported = imports.get(prefix)
        if imported and "::" not in imported:
            return modules.get(imported, {}).get(remainder)
        if imported and remainder:
            return imported.rsplit("::", 1)[0] + "::" + remainder
        if prefix == "self" and caller.rsplit(".", 1)[0] in classes:
            return own.get(f"{caller.rsplit('.', 1)[0]}.{remainder}")
    return None


def _matching_nodes(function_name: str, functions: dict[str, FunctionInfo]) -> set[str]:
    return {
        node
        for node, function in functions.items()
        if node == function_name or function.qualified_name == function_name or function.name == function_name
    }


def build_call_graph(files: dict[str, str]) -> CallGraph:
    """Parse an in-memory path-to-source mapping and return its call graph."""
    from .code_parser import parse_file

    return CallGraph({path: parse_file(source) for path, source in files.items()})