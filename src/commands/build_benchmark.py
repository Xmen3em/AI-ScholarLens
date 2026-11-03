"""Build and check the paper benchmark manifests. Default performs no network work."""

import argparse
import asyncio
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
from src.policies.ai_scope import AI_CATEGORY_ALLOWLIST
from src.services.study.content import PaperContent
from src.services.study.intake import StudyPaper

ROOT = Path("evaluation/paper_benchmark")
DATA = Path("data/eval/paper-benchmark")
FIELDS = ("ml_nlp", "medicine", "physics", "biology", "economics", "systems")
ALLOWED_LICENSES = frozenset({
    "http://creativecommons.org/licenses/by/4.0/",
    "http://creativecommons.org/licenses/by-sa/4.0/",
    "http://creativecommons.org/publicdomain/zero/1.0/",
})
# Seen before the benchmark existed: kept in development, never published if its license forbids it.
PRIVATE_PAPER = "2510.26807"
TUNED_PAPER = "2005.11401"
MAX_PAGES = 40
OAI_URL = "https://oaipmh.arxiv.org/oai"
FEATURES = frozenset({"table_result", "equation_method"})


def base_id(identity: str) -> str:
    return re.sub(r"v\d+$", "", identity)


def parse_license(body: bytes) -> str | None:
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)", body, re.IGNORECASE):
        raise ValueError("invalid_metadata")
    root = ET.fromstring(body)
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "license" and element.text:
            return element.text.strip()
    return None


def admit(candidate: dict, content: PaperContent, license_url: str | None) -> dict:
    publish = license_url in ALLOWED_LICENSES
    if not publish and not candidate.get("allow_private"):
        raise ValueError("license")
    if content.page_count > MAX_PAGES:
        raise ValueError("pages")
    if not content.blocks or content.coverage not in {"full_text", "partial_text"}:
        raise ValueError("no_text")
    if not set(content.paper.categories) & AI_CATEGORY_ALLOWLIST:
        raise ValueError("outside_ai_scope")
    return {"id": content.paper.arxiv_id, "field": candidate["field"], "split": None, "license": license_url,
            "publish": publish, "categories": content.paper.categories, "pages": content.page_count,
            "blocks": len(content.blocks), "sha256": content.source_sha256,
            "parser_revision": content.parser_revision, "features": candidate["features"]}


def select(rows: list[dict]) -> list[dict]:
    # Candidate order decides: the first five admitted per field, the first two of them for development.
    chosen = []
    for field in FIELDS:
        for index, row in enumerate([row for row in rows if row["field"] == field][:5]):
            chosen.append({**row, "split": "dev" if index < 2 else "holdout"})
    return chosen


def check_manifest(manifest: dict) -> None:
    rows = manifest["papers"]
    ids = [base_id(row["id"]) for row in rows]
    if len(rows) != 30 or len(set(ids)) != 30:
        raise ValueError("count")
    if TUNED_PAPER in ids:
        raise ValueError("tuned_paper")
    for field in FIELDS:
        group = [row for row in rows if row["field"] == field]
        if len(group) != 5 or sum(row["split"] == "dev" for row in group) != 2:
            raise ValueError("split")
        if sum(row["split"] == "holdout" for row in group) != 3:
            raise ValueError("split")
        features = {feature for row in group for feature in row["features"]}
        if not FEATURES <= features:
            raise ValueError("features")
    for row in rows:
        if not set(row["features"]) <= FEATURES:
            raise ValueError("features")
        if row["publish"] != (row["license"] in ALLOWED_LICENSES):
            raise ValueError("publish")
        if not row["publish"] and base_id(row["id"]) != PRIVATE_PAPER:
            raise ValueError("publish")
        if not set(row["categories"]) & AI_CATEGORY_ALLOWLIST:
            raise ValueError("scope")
        if row["pages"] > MAX_PAGES or row["blocks"] < 1 or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            raise ValueError("source")
    private = [row for row in rows if base_id(row["id"]) == PRIVATE_PAPER]
    if len(private) != 1 or private[0]["field"] != "medicine" or private[0]["split"] != "dev":
        raise ValueError("diabetes")


KINDS = ("Q1", "Q2", "Q3")
ARXIV_ID = re.compile(r"\d{4}\.\d{4,5}|[A-Za-z][A-Za-z.-]{1,24}/\d{7}")
PRIVATE_QUESTIONS = DATA / "private-questions.json"


def _flat(text: str) -> str:
    return " ".join(text.split())


def _opens_paper(text: str) -> bool:
    # The service would read these as a new paper or a command instead of a follow-up.
    stripped = text.strip()
    return stripped.startswith(("/", "http:", "https:")) or bool(ARXIV_ID.search(stripped)) or len(stripped) > 512


def check_questions(questions: dict, papers: dict, contents: dict[str, PaperContent] | None) -> None:
    rows = questions["papers"]
    for paper in papers["papers"]:
        entry = rows.get(paper["id"])
        if type(entry) is not dict or set(entry) != set(KINDS):
            raise ValueError("shape: " + paper["id"])
        for kind in KINDS:
            text = entry[kind].get("text", "")
            if not text.strip():
                raise ValueError("shape: " + paper["id"])
            if _opens_paper(text):
                raise ValueError("question_opens_paper: " + paper["id"] + " " + kind)
        for kind in ("Q1", "Q2"):
            facts = entry[kind].get("facts", [])
            if not 1 <= len(facts) <= 3 or any(not fact["fact"].strip() or not 0 < len(fact["quote"]) <= 300 for fact in facts):
                raise ValueError("facts: " + paper["id"] + " " + kind)
        if not entry["Q3"].get("absent_terms") or entry["Q3"].get("hits") != 0:
            raise ValueError("shape: " + paper["id"] + " Q3")
        if contents is None:
            continue
        document = contents[paper["id"]]
        blocks = {block.id: _flat(block.text) for block in document.blocks}
        for kind in ("Q1", "Q2"):
            for fact in entry[kind]["facts"]:
                if _flat(fact["quote"]) not in blocks.get(fact["block"], ""):
                    raise ValueError("quote_missing: " + paper["id"] + " " + kind + " " + fact["block"])
        whole = " ".join(blocks.values()).casefold()
        for term in entry["Q3"]["absent_terms"]:
            if term.casefold() in whole:
                raise ValueError("q3_terms_present: " + paper["id"] + " " + term)
    if set(rows) != {paper["id"] for paper in papers["papers"]}:
        raise ValueError("shape: unexpected papers")


def load_questions(root: Path = ROOT, private: Path = PRIVATE_QUESTIONS) -> dict:
    questions = json.loads((root / "questions.v1.json").read_text(encoding="utf-8"))
    if private.exists():
        questions["papers"].update(json.loads(private.read_text(encoding="utf-8"))["papers"])
    return questions


def load_contents(papers: dict, root: Path = DATA / "content") -> dict[str, PaperContent]:
    contents = {}
    for paper in papers["papers"]:
        path = root / (paper["id"] + ".json")
        if path.exists():
            contents[paper["id"]] = PaperContent.model_validate_json(path.read_text(encoding="utf-8"))
    return contents


def spot_check_sheet(questions: dict, papers: dict, seed: int = 20261103) -> str:
    import random

    picker = random.Random(seed)
    items = []
    for field in FIELDS:
        group = [row["id"] for row in papers["papers"] if row["field"] == field]
        items += [(field, paper, kind) for paper in group for kind in KINDS]
    chosen = []
    for field in FIELDS:
        chosen += picker.sample([item for item in items if item[0] == field], 3)
    rest = [item for item in items if item not in chosen]
    chosen += picker.sample(rest, 20 - len(chosen))
    lines = ["# Question spot-check", "", "Mark each: ok / fix (and why). Check the Arabic reads naturally, the facts",
             "answer the question, and Q3 really is not answered by the paper.", ""]
    for field, paper, kind in chosen:
        entry = questions["papers"][paper][kind]
        lines += [f"## {paper} {kind} ({field})", "", entry["text"], ""]
        for fact in entry.get("facts", []):
            lines += [f"- {fact['fact']}", f"  > {fact['quote']} [{fact['block']}]"]
        if "absent_terms" in entry:
            lines.append("- absent terms: " + ", ".join(entry["absent_terms"]))
        lines += ["", "Verdict: ", ""]
    return "\n".join(lines)


FROZEN_FILES = ("PROTOCOL.md", "papers.v1.json", "questions.v1.json", "models.v1.json")


def _digests(root: Path, private: Path | None) -> dict[str, str]:
    import hashlib

    digests = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in FROZEN_FILES}
    if private is not None and private.exists():
        # Hash only: the private questions stay out of the repository.
        digests["private-questions.json"] = hashlib.sha256(private.read_bytes()).hexdigest()
    return digests


def _manifest_hash(digests: dict[str, str]) -> str:
    import hashlib

    return hashlib.sha256(json.dumps(digests, sort_keys=True).encode()).hexdigest()


def freeze(root: Path = ROOT, private: Path | None = None) -> dict:
    from datetime import date

    digests = _digests(root, private)
    manifest = {"version": "paper-benchmark-v1", "frozen_on": date.today().isoformat(), "sha256": digests,
                "manifest_sha256": _manifest_hash(digests)}
    write_json(root / "manifest.json", manifest)
    return manifest


def verify_frozen(root: Path = ROOT, private: Path | None = None) -> str:
    path = root / "manifest.json"
    if not path.exists():
        raise ValueError("manifest_missing")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    digests = _digests(root, private)
    if digests != manifest["sha256"] or _manifest_hash(digests) != manifest["manifest_sha256"]:
        raise ValueError("manifest_changed")
    return manifest["manifest_sha256"]


def parse_raw(body: bytes) -> tuple[StudyPaper, str | None]:
    """One OAI arXivRaw record: the latest version's metadata and its license (no export-API call)."""
    from email.utils import parsedate_to_datetime

    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)", body, re.IGNORECASE):
        raise ValueError("invalid_metadata")
    root = ET.fromstring(body)
    record = next((element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "arXivRaw"), None)
    if record is None:
        raise ValueError("invalid_metadata")

    def text(name: str) -> str:
        found = next((child for child in record if child.tag.rsplit("}", 1)[-1] == name), None)
        return " ".join((found.text or "").split()) if found is not None else ""

    versions = [child for child in record if child.tag.rsplit("}", 1)[-1] == "version"]
    if not versions:
        raise ValueError("invalid_metadata")
    first_date = next(child.text for child in versions[0] if child.tag.rsplit("}", 1)[-1] == "date")
    authors = [name.strip() for name in re.split(r",| and ", text("authors")) if name.strip()]
    paper = StudyPaper(arxiv_id=text("id") + versions[-1].attrib["version"], title=text("title"),
                       authors=authors[:30], author_count=len(authors), abstract=text("abstract"),
                       categories=text("categories").split(),
                       published=parsedate_to_datetime(first_date or "").isoformat())
    return paper, text("license") or None


async def fetch_raw(client: httpx.AsyncClient, identity: str) -> tuple[StudyPaper, str | None]:
    for wait in (10, 30, 60, 0):
        response = await client.get(OAI_URL, params={"verb": "GetRecord", "metadataPrefix": "arXivRaw",
                                                     "identifier": "oai:arXiv.org:" + base_id(identity)}, timeout=60)
        if response.status_code in {429, 503} and wait:
            # OAI asks clients to back off; honour it instead of rejecting the paper.
            await asyncio.sleep(int(response.headers.get("Retry-After", wait)))
            continue
        response.raise_for_status()
        break
    return parse_raw(response.content)


async def build_papers() -> dict:
    from src.services.study.content import ContentError, PaperContentService

    candidates = json.loads((ROOT / "candidates.v1.json").read_text(encoding="utf-8"))["candidates"]
    (DATA / "content").mkdir(parents=True, exist_ok=True)
    admitted: list[dict] = []
    rejected: list[dict] = []
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=60,
                                 headers={"User-Agent": "ScholarLens-benchmark/0.1"}) as client:
        service = PaperContentService(DATA / "sources", client)
        for candidate in candidates:
            if sum(row["field"] == candidate["field"] for row in admitted) >= 5:
                continue
            try:
                await asyncio.sleep(3)
                paper, license_url = await fetch_raw(client, candidate["id"])
                cached = DATA / "content" / (paper.arxiv_id + ".json")
                if cached.exists():
                    # A rerun reuses parsed content instead of downloading the PDF again.
                    document = PaperContent.model_validate_json(cached.read_text(encoding="utf-8"))
                else:
                    document = await service.acquire(paper)
                row = admit(candidate, document, license_url)
            except (ValueError, ContentError, httpx.HTTPError) as exc:
                reason = getattr(exc, "code", None) or str(exc) or type(exc).__name__
                rejected.append({"id": candidate["id"], "field": candidate["field"], "reason": reason})
                print("rejected", candidate["id"], reason, flush=True)
                continue
            (DATA / "content" / (document.paper.arxiv_id + ".json")).write_text(
                document.model_dump_json(), encoding="utf-8", newline="\n")
            admitted.append(row)
            print("admitted", row["id"], row["field"], flush=True)
    return {"version": "paper-benchmark-papers-v1", "papers": select(admitted), "rejected": rejected}


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["papers", "questions", "spot-check", "freeze"])
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "papers":
        if not args.execute:
            print("Would read candidates.v1.json, fetch licenses, metadata and PDFs from arXiv, and write "
                  "papers.v1.json. Re-run with --execute.")
            return 0
        manifest = asyncio.run(build_papers())
        write_json(ROOT / "papers.v1.json", manifest)
        check_manifest(manifest)
        print("papers ok:", len(manifest["papers"]))
    elif args.command in {"questions", "spot-check"}:
        papers = json.loads((ROOT / "papers.v1.json").read_text(encoding="utf-8"))
        questions = load_questions()
        contents = load_contents(papers)
        check_questions(questions, papers, contents if len(contents) == len(papers["papers"]) else None)
        if args.command == "spot-check":
            DATA.mkdir(parents=True, exist_ok=True)
            (DATA / "spot-check.md").write_text(spot_check_sheet(questions, papers), encoding="utf-8", newline="\n")
            print("spot-check sheet:", DATA / "spot-check.md")
        print("questions ok:", 3 * len(papers["papers"]), "contents checked:", len(contents))
    elif args.command == "freeze":
        papers = json.loads((ROOT / "papers.v1.json").read_text(encoding="utf-8"))
        check_manifest(papers)
        contents = load_contents(papers)
        if len(contents) != len(papers["papers"]):
            raise SystemExit("every paper's parsed content must be cached before freezing")
        check_questions(load_questions(), papers, contents)
        print("frozen:", freeze(ROOT, PRIVATE_QUESTIONS)["manifest_sha256"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
