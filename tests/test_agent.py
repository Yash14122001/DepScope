from src.agent import AnalysisContext, make_tools, run_agent
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


def test_repository_search_tools_cover_general_questions():
    files = {"config.py": "API_URL = 'https://example.com'\n", "main.py": "def run():\n    pass\n"}
    by_name = {tool.__name__: tool for tool in make_tools(AnalysisContext(build_call_graph(files), files=files))}

    assert by_name["list_files"](".py") == ["config.py", "main.py"]
    assert by_name["search_text"]("api_url") == [{"path": "config.py", "line": 1, "text": "API_URL = 'https://example.com'"}]


def test_agent_retries_transient_connection_resets():
    class Response:
        function_calls = []
        text = "Answer"

    class Models:
        calls = 0

        def generate_content(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise ConnectionResetError(10054, "connection reset")
            return Response()

    class Client:
        models = Models()

    result = run_agent(Client(), "hello", [])

    assert result.answer == "Answer"
    assert Client.models.calls == 2