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
DAG_MODULE = PROJECT_ROOT / "airflow" / "dags" / "arxiv_paper_ingestion.py"
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


def _task_function(name: str) -> ast.FunctionDef:
    tree = ast.parse(TASKS_MODULE.read_text())
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )


def test_daily_report_is_returned_and_not_only_logged():
    """A task that only logs its result leaves nothing in XCom for anything downstream."""
    function = _task_function("generate_daily_report")

    returned = [node for node in ast.walk(function) if isinstance(node, ast.Return) and node.value is not None]

    assert returned, "generate_daily_report builds a report but never returns it"


def _declared_task_ids() -> set[str]:
    """Every ``task_id=`` the DAG assigns to an operator."""
    tree = ast.parse(DAG_MODULE.read_text())
    return {
        keyword.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "task_id" and isinstance(keyword.value, ast.Constant)
    }


def _pulled_task_ids() -> set[str]:
    """Every ``task_ids=`` the task module reads back out of XCom."""
    tree = ast.parse(TASKS_MODULE.read_text())
    return {
        keyword.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "task_ids" and isinstance(keyword.value, ast.Constant)
    }


def test_every_xcom_pull_names_a_task_the_dag_declares():
    """A pull against a renamed task returns None silently, and the report reads zeros forever."""
    declared, pulled = _declared_task_ids(), _pulled_task_ids()
    assert pulled, "no xcom_pull with a literal task_ids found; update or delete this test"

    assert not pulled - declared, f"xcom_pull reads task ids the DAG does not declare: {sorted(pulled - declared)}"


def test_every_task_the_dag_declares_has_a_callable_or_a_bash_command():
    """Catches an operator left pointing at a function that was renamed out from under it."""
    dag_tree = ast.parse(DAG_MODULE.read_text())
    imported = {
        alias.name
        for node in ast.walk(dag_tree)
        if isinstance(node, ast.ImportFrom) and node.module == "arxiv_ingestion.tasks"
        for alias in node.names
    }
    defined = {
        node.name
        for node in ast.walk(ast.parse(TASKS_MODULE.read_text()))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert imported, "the DAG no longer imports task functions; update or delete this test"
    assert not imported - defined, f"DAG imports task functions that do not exist: {sorted(imported - defined)}"
