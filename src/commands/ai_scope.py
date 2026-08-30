"""Audit and purge stored papers against the AI category allowlist.

    python -m src.commands.ai_scope audit
    python -m src.commands.ai_scope purge --expected-count N [--apply]

The scope predicate is imported from src.policies.ai_scope, the same one the ingestion
pipeline enforces. Re-expressing it as SQL here would let the two drift apart, and the
half that drifts is the half that deletes rows.
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from typing import List, Optional, Sequence

from src.database import get_db_session
from src.policies.ai_scope import AI_CATEGORY_ALLOWLIST, matches_ai_scope
from src.repositories.paper import CategoryRow, PaperRepository

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_VIOLATIONS_FOUND = 3
EXIT_COUNT_MISMATCH = 4


@dataclass(frozen=True)
class ScopeReport:
    """What a full scan of the papers table found."""

    scanned: int
    violations: List[CategoryRow]

    @property
    def compliant(self) -> int:
        return self.scanned - len(self.violations)


@dataclass(frozen=True)
class ScopeOutcome:
    """What a command decided and did, before anything is rendered."""

    command: str
    report: ScopeReport
    exit_code: int
    applied: bool = False
    deleted: int = 0


def scan(repository: PaperRepository, *, for_update: bool = False) -> ScopeReport:
    """Classify every stored paper against the allowlist."""
    rows = repository.list_all_categories(for_update=for_update)
    return ScopeReport(scanned=len(rows), violations=[row for row in rows if not matches_ai_scope(row.categories)])


def render(outcome: ScopeOutcome, *, as_json: bool = False) -> None:
    """Write the report to stdout. Logs stay on stderr, so --json stays pipe-safe."""
    report = outcome.report
    if as_json:
        json.dump(
            {
                "command": outcome.command,
                "allowlist": sorted(AI_CATEGORY_ALLOWLIST),
                "scanned": report.scanned,
                "compliant": report.compliant,
                "non_compliant": len(report.violations),
                "applied": outcome.applied,
                "deleted": outcome.deleted,
                "papers": [
                    {"id": str(row.id), "arxiv_id": row.arxiv_id, "categories": row.categories} for row in report.violations
                ],
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return

    print(f"Allowlist:      {', '.join(sorted(AI_CATEGORY_ALLOWLIST))}")
    print(f"Scanned:        {report.scanned}")
    print(f"Compliant:      {report.compliant}")
    print(f"Non-compliant:  {len(report.violations)}")
    if report.violations:
        print()
        print(f"{'ARXIV ID':<20} {'ID':<38} CATEGORIES")
        for row in report.violations:
            print(f"{row.arxiv_id:<20} {str(row.id):<38} {row.categories}")
    if outcome.applied:
        print()
        print(f"Deleted:        {outcome.deleted}")


def _log_scan(report: ScopeReport) -> None:
    logger.info("Scanned %d papers: %d compliant, %d non-compliant", report.scanned, report.compliant, len(report.violations))


def run_audit(repository: PaperRepository, *, fail_on_violation: bool = False) -> ScopeOutcome:
    """Report scope compliance. Never writes."""
    report = scan(repository)
    _log_scan(report)
    exit_code = EXIT_VIOLATIONS_FOUND if report.violations and fail_on_violation else EXIT_OK
    return ScopeOutcome(command="audit", report=report, exit_code=exit_code)


def run_purge(repository: PaperRepository, *, expected_count: Optional[int], apply: bool = False) -> ScopeOutcome:
    """Delete non-compliant papers. Writes nothing unless ``apply`` is true.

    When applying, the scan takes SELECT ... FOR UPDATE row locks that are held until
    the commit below, so a concurrent ingestion run cannot update a paper between the
    count that authorises the delete and the delete itself. Rows inserted after the
    lock are not covered, which is intended: the invariant is "never delete a compliant
    paper", not "catch every violation in a single pass".
    """
    report = scan(repository, for_update=apply)
    _log_scan(report)

    if expected_count is not None and len(report.violations) != expected_count:
        repository.session.rollback()  # Release the locks now rather than at process exit.
        logger.error(
            "Aborting: expected %d non-compliant papers, found %d. Nothing was deleted.",
            expected_count,
            len(report.violations),
        )
        return ScopeOutcome(command="purge", report=report, exit_code=EXIT_COUNT_MISMATCH)

    if not apply:
        logger.info(
            "Dry run. Re-run with --expected-count %d --apply to delete %d papers.",
            len(report.violations),
            len(report.violations),
        )
        return ScopeOutcome(command="purge", report=report, exit_code=EXIT_OK)

    # Deletes exactly the ids that were counted, not a re-evaluated predicate.
    deleted = repository.delete_by_ids([row.id for row in report.violations])
    repository.session.commit()
    logger.info("Deleted %d non-compliant papers.", deleted)
    return ScopeOutcome(command="purge", report=report, exit_code=EXIT_OK, applied=True, deleted=deleted)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.commands.ai_scope",
        description="Report and remove stored papers outside the AI category allowlist.",
    )
    parser.add_argument("--json", action="store_true", help="Emit a JSON report on stdout instead of a table.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="Report scope compliance. Never writes.")
    audit.add_argument(
        "--fail-on-violation",
        action="store_true",
        help=f"Exit {EXIT_VIOLATIONS_FOUND} when any non-compliant paper is found.",
    )

    purge = subparsers.add_parser("purge", help="Delete non-compliant papers. Dry run unless --apply is given.")
    purge.add_argument("--apply", action="store_true", help="Actually delete. Without it, nothing is written.")
    purge.add_argument(
        "--expected-count",
        type=int,
        metavar="N",
        help="Abort unless exactly N papers are non-compliant. Required with --apply.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "purge" and args.apply and args.expected_count is None:
        parser.error("--apply requires --expected-count N (run without --apply first to learn N).")

    try:
        with get_db_session() as session:
            repository = PaperRepository(session)
            if args.command == "audit":
                outcome = run_audit(repository, fail_on_violation=args.fail_on_violation)
            else:
                outcome = run_purge(repository, expected_count=args.expected_count, apply=args.apply)
            render(outcome, as_json=args.json)
            return outcome.exit_code
    except Exception:
        logger.exception("ai_scope failed")
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
