from eval.run_eval import evaluate_dataset, score_case


def test_score_case_calculates_precision_and_recall():
    result = score_case(["caller.py::run"], ["caller.py::run", "other.py::noise"])

    assert result["precision"] == 0.5
    assert result["recall"] == 1.0


def test_dataset_runner_scores_graph_predictions():
    result = evaluate_dataset([{
        "id": "small",
        "files": {
            "utils.py": "def helper():\n    pass\n",
            "main.py": "from utils import helper\ndef run():\n    helper()\n",
        },
        "target": "helper",
        "expected_direct_callers": ["main.py::run"],
    }])

    assert result["case_count"] == 1
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0