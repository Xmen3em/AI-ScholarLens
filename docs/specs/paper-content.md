# paper-content: structured sources and qualified extraction

Status: extension spec, 21 October 2026. Inherits [shared rules](researcher-app.md).
Depends on paper-intake; provides source content/regions to paper-evidence.

## Objective and baseline

Give the tutor readable source material while showing exactly which pages,
structures or symbols could not be read. Native PDFium extraction already uses
an isolated credential-free worker, PDF hash, parser revision, page blocks and
coverage flags. Current native limits include 20 MiB/45 pages; source cache is
bounded at 256 MiB. Existing OCR adapter is disabled and unqualified live.

## Provider contracts

Keep existing `PaperContent`/`EvidenceBlock` compatible. Add an independently
versioned `SourceManifest` keyed by explicit paper/version, PDF hash, parser/
extraction revision and source-format identity. A structured HTML representation
must record its own hash and a verified correspondence to the selected paper;
do not assume HTML and PDF page offsets are interchangeable.

`SourceRegion` carries stable region ID, kind (`paragraph`, `table`, `equation`,
`figure`, `caption`), page, bounded normalized rectangle when available, reading
order and origin (`native`, `ocr`, `reviewed`). Preserve exact extracted text
separately from normalized search/display text. Unknown geometry stays unknown.

`ExtractionReport` lists page/region coverage, truncation, warnings, extraction
model/provider/revision and attempted operations. Do not convert a model's
self-reported confidence into verified accuracy. A source region can exist with
an unavailable structured interpretation; readable prose does not prove tables
or equations were read correctly.

## Extraction sequence and failures

1. Use reviewed native structure where extractable; compare structured HTML as
   an optional later adapter, not an implicit replacement source.
2. Detect missing/scanned/multicolumn or damaged regions and preserve flags.
3. After separate model/route qualification and admission, OCR only the needed
   bounded pages/regions. Do not send every page automatically or activate a GPU.
4. Validate outputs against page images/regions and a reviewed scientific set.
   Store original images/text and derived interpretations separately.

Missing signs, merged table columns and wrong reading order are critical cases.
On OCR failure, return native coverage and the unreadable region; do not silently
replace a quote or retry another provider. Later user-supplied PDF attachments
use the same parser isolation, byte/page caps and upload admission contract.

## Implementation and commands

Existing paths: `content.py`, `pdf_worker.py`, `ocr.py`. Proposed additions:
`source_manifest.py` and a separate structured worker/adapter; split changes into
at most five files each. Use strict Pydantic contracts and fixed worker programs;
never run source/model instructions or expose credentials to native parsers.

```powershell
.venv-win/Scripts/python.exe -m pytest tests/unit/test_study_content.py tests/unit/test_study_ocr.py -q -o cache_dir=tests/test_output/study-pytest --basetemp tests/test_output/content-contract
```

New region/structure tests use tiny committed or generated PDFs/images with known
answers; CI must not depend on the ignored cached full RAG PDF. Qualify the real
parser separately from stubbed hosted boundaries. Use common lint/type checks.

## Acceptance and decisions

PC-1: Region references resolve only against the exact source/revision; malformed,
oversize, scanned and interrupted parser cases preserve bounded safe outcomes.

PC-2: A reviewed fixture of two-column prose, table headers/cells, equation signs
and figure captions records zero unflagged critical extraction errors. Unreadable
regions are explicit and cannot enter verified numeric/causal claims.

PC-3: OCR sends only admitted content, records failed/unknown attempts, meets a
measured worker envelope and leaves native reading usable when unavailable.

Candidate models/terms/routes remain those in the saved research until rechecked.
Select by scientific extraction and actual hosted capabilities, not model size.
No new weights, paid calls or endpoint are authorized by this spec.
