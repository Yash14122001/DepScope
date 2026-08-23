# Evaluation Results

This baseline uses the deterministic AST call graph, not Gemini.

- Cases: 2
- Precision: 100.0%
- Recall: 100.0%

## Cases

- `imported-helper`: precision 100.0%, recall 100.0%, predicted `['service.py::process']`
- `method-caller`: precision 100.0%, recall 100.0%, predicted `['worker.py::Worker.run']`
