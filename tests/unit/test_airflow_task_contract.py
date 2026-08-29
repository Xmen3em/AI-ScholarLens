"""Guards the contract between the Airflow DAG and the metadata fetcher it drives.

Neither module can be imported in the fast suite: the DAG needs Airflow and the
container's ``/opt/airflow`` path, and ``MetadataFetcher`` pulls in Docling, which
only exists in the Airflow image. Both sides are therefore compared statically,
so a rename or a dropped keyword argument on either side fails here instead of at
DAG runtime.
"""

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
TASKS_MODULE = PROJECT_ROOT / "airflow" / "dags" / "arxiv_ingestion" / "tasks.py"
FETCHER_MODULE = PROJECT_ROOT / "src" / "services" / "metadata_fetcher.py"


def _fetcher_calls_in_dag() -> list[ast.Call]:
    tree = ast.parse(TASKS_MODULE.read_text())
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "metadata_fetcher"
    ]


def _fetcher_methods() -> dict[str, set[str]]:
    """Map each ``MetadataFetcher`` method to the parameter names it accepts."""
    tree = ast.parse(FETCHER_MODULE.read_text())
    class_node = next(
        node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == "MetadataFetcher"
    )
    methods = {}
    for node in class_node.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            methods[node.name] = {
                arg.arg for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]
            }
    return methods


@pytest.fixture(scope="module")
def dag_calls() -> list[ast.Call]:
    calls = _fetcher_calls_in_dag()
    if not calls:
        pytest.fail("the DAG no longer calls the metadata fetcher; update or delete this contract test")
    return calls


def test_dag_only_calls_metadata_fetcher_methods_that_exist(dag_calls):
    methods = _fetcher_methods()

    missing = sorted({call.func.attr for call in dag_calls if call.func.attr not in methods})

    assert not missing, f"DAG calls metadata fetcher methods that do not exist: {missing}"


def test_dag_passes_only_arguments_the_metadata_fetcher_accepts(dag_calls):
    methods = _fetcher_methods()

    unknown_by_method = {}
    for call in dag_calls:
        accepted = methods.get(call.func.attr)
        if accepted is None:
            continue  # reported by the method-existence test
        passed = {keyword.arg for keyword in call.keywords if keyword.arg is not None}
        if passed - accepted:
            unknown_by_method[call.func.attr] = sorted(passed - accepted)

    assert not unknown_by_method, f"DAG passes unknown arguments: {unknown_by_method}"
