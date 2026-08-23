from src.agent import AnalysisContext, make_tools
from src.call_graph import build_call_graph


def test_tools_return_structured_graph_and_file_evidence():
    files = {
        "utils.py": "def helper(value):\n    return value\n",
        "main.py": "from utils import helper\ndef run(value):\n    return helper(value)\n",
    }
    tools = make_tools(AnalysisContext(build_call_graph(files), files=files))
    by_name = {tool.__name__: tool for tool in tools}

    assert by_name["get_callers"]("helper") == [{"caller": "main.py::run", "callee": "utils.py::helper", "line": 3, "dynamic": False}]
    assert by_name["read_file"]("main.py", 2, 3) == "2: def run(value):\n3:     return helper(value)"


def test_tools_are_json_serializable():
    files = {"main.py": "def run():\n    pass\n"}
    tools = make_tools(AnalysisContext(build_call_graph(files), files=files))

    import json
    json.dumps({"results": tools[0]("run")})