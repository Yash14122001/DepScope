from src.code_parser import parse_file


SOURCE = """
from utils import helper as imported_helper
import services.api as api

def outer(value):
    \"\"\"Call a helper.\"\"\"
    imported_helper(value)
    api.send(value)
    getattr(api, \"send\")(value)

    def inner():
        return value

class Worker:
    async def run(self):
        return self.finish()

    def finish(self):
        return outer(1)
"""


def test_extracts_functions_docstrings_lines_and_calls():
    result = parse_file(SOURCE)

    assert [(item.qualified_name, item.line) for item in result.functions] == [
        ("outer", 5),
        ("outer.inner", 11),
        ("Worker.run", 15),
        ("Worker.finish", 18),
    ]
    outer_calls = [call for call in result.calls if call.caller == "outer"]
    assert [call.name for call in outer_calls] == ["imported_helper", "api.send", "unknown/dynamic", "getattr"]
    assert outer_calls[2].dynamic


def test_records_dynamic_calls_and_import_aliases():
    result = parse_file(SOURCE)

    dynamic_calls = [call for call in result.calls if call.name == "unknown/dynamic"]
    assert len(dynamic_calls) == 1
    assert [(item.module, item.name, item.alias) for item in result.imports] == [
        ("utils", "helper", "imported_helper"),
        ("services.api", None, "api"),
    ]