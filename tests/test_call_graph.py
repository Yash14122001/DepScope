from src.call_graph import UNKNOWN_DYNAMIC, build_call_graph


FILES = {
    "utils.py": "def helper(value):\n    return value\n",
    "service.py": "from utils import helper as imported_helper\n\ndef run(value):\n    return imported_helper(value)\n",
    "services/api.py": "def send(value):\n    return value\n",
    "client.py": "import services.api as api\n\ndef call_api(value):\n    return api.send(value)\n",
    "worker.py": "class Worker:\n    def run(self):\n        return self.finish()\n\n    def finish(self):\n        return getattr(self, 'save')()\n",
}


def test_resolves_imported_calls_and_finds_callers():
    graph = build_call_graph(FILES)

    callers = graph.find_callers("helper")

    assert [(edge.caller, edge.callee, edge.line) for edge in callers] == [("service.py::run", "utils.py::helper", 4)]

    api_callers = graph.find_callers("send")
    assert [(edge.caller, edge.callee) for edge in api_callers] == [("client.py::call_api", "services/api.py::send")]


def test_resolves_self_methods_and_preserves_dynamic_calls():
    graph = build_call_graph(FILES)

    callees = graph.find_callees("Worker.run")
    dynamic = graph.find_callees("Worker.finish")

    assert [(edge.caller, edge.callee) for edge in callees] == [("worker.py::Worker.run", "worker.py::Worker.finish")]
    assert dynamic[0].callee == UNKNOWN_DYNAMIC
    assert dynamic[0].dynamic