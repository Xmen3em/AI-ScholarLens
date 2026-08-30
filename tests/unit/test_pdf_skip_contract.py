"""The contract that keeps a declined PDF distinguishable from a broken one.

`docling.py` cannot be imported in the fast suite — docling and pypdfium2 exist only in
the Airflow image — so the parts that can be checked without importing it are checked
statically, in the same way `test_airflow_task_contract.py` handles the DAG.
"""

import ast
from pathlib import Path

from src.exceptions import PDFParsingException, PDFSkippedError, PDFValidationError

DOCLING_MODULE = Path(__file__).parents[2] / "src" / "services" / "pdf_parser" / "docling.py"


def test_a_skip_is_not_a_validation_failure():
    """The distinction is the whole point: one means "our limits say no", the other
    means "this file is broken". Making PDFSkippedError a PDFValidationError would let
    every `except PDFValidationError` swallow skips again."""
    assert issubclass(PDFSkippedError, PDFParsingException)
    assert not issubclass(PDFSkippedError, PDFValidationError)
    assert not issubclass(PDFValidationError, PDFSkippedError)


def _handlers_of(function_name: str) -> list[ast.ExceptHandler]:
    tree = ast.parse(DOCLING_MODULE.read_text())
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
    )
    return [node for node in ast.walk(function) if isinstance(node, ast.ExceptHandler)]


def _names_in(handler: ast.ExceptHandler) -> set[str]:
    if handler.type is None:
        return set()
    caught = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return {node.id for node in caught if isinstance(node, ast.Name)}


def test_validate_pdf_reraises_a_skip_instead_of_rewrapping_it():
    """Its catch-all wraps anything unnamed into PDFValidationError, which silently
    turned every page-limit skip into a validation failure until PDFSkippedError was
    named here."""
    reraised = {
        name
        for handler in _handlers_of("_validate_pdf")
        if all(isinstance(node, ast.Raise) and node.exc is None for node in handler.body)
        for name in _names_in(handler)
    }

    assert "PDFSkippedError" in reraised, "_validate_pdf must re-raise PDFSkippedError before its catch-all"


def test_parse_pdf_lets_a_skip_propagate():
    """Returning None here is what discarded the reason in the first place."""
    handlers = _handlers_of("parse_pdf")
    skip_handlers = [h for h in handlers if "PDFSkippedError" in _names_in(h)]

    assert skip_handlers, "parse_pdf must handle PDFSkippedError explicitly"
    for handler in skip_handlers:
        returns = [node for node in ast.walk(handler) if isinstance(node, ast.Return)]
        assert not returns, "a skip must propagate with its reason, not become a bare return"
