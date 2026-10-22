# Arabic reading: mixed Arabic/English presentation

Status: contract with an offline viewer/rendering subset implemented,
22 October 2026. This records the
owner's requirement for comfortable Egyptian Arabic reading alongside English
terms. It applies to lessons, citations, visual labels, the future viewer and
Telegram delivery. The [implemented subset](../visual-learning-implementation.ar.md)
uses bounded text runs, explicit HTML isolation, app-owned SVG direction and
measured Windows PNG labels. Twelve shared cases have browser checks; actual
Telegram clients, editable question input and arbitrary new visual labels remain
future qualification. Build them within [learning-visuals](learning-visuals.md);
keep the existing bot behavior until its separate delivery checks pass.

## Content and presentation boundaries

Keep canonical Unicode text in logical reading order. Never reverse strings,
store Arabic presentation-form glyphs, reorder words for display, translate an
identifier or change a reported value. Source hashes, exact quotations and
evidence offsets refer to canonical content, not decorated output. Bidirectional
ordering and Arabic glyph shaping are separate renderer responsibilities.
[Unicode bidirectional algorithm](https://www.unicode.org/reports/tr9/).

Use one small application-owned text policy, not another model or agent. The
model supplies language/content; the application decides direction, isolation,
escaping and layout. Prefer semantic runs for application-known terms, code,
numeric values, citations and links. Use an isolated auto-direction container
for unknown titles/phrases. Avoid a regex that wraps every Latin character:
multiword terms and their internal punctuation need to stay together.

Do not change the existing source/evidence schema for display needs. Any new
text-run contract belongs to the visual/presentation layer, is finite and bounded
by the existing visual-spec limit, and cannot contain HTML, CSS or executable code.

## Browser reading and input

- Set the Egyptian lesson shell to `lang="ar-EG" dir="rtl"`. Direction and
  language are separate attributes. Keep teaching paragraphs RTL even when the
  first term is English; reserve `dir="auto"` for unknown/user-supplied blocks.
- Wrap known English phrases with `<bdi dir="ltr" lang="en">`; use `<bdi>` for
  unknown-direction inserts. Isolate the whole semantic phrase, including its
  own brackets/signs, while leaving the surrounding Arabic punctuation outside.
- Give original English quotations their own `lang="en" dir="ltr"` block.
  Display equations and code in separate LTR regions with a readable Arabic
  explanation beside/below them. Math comparisons must preserve operand order.
- Give the question input `dir="auto"`; do not mutate the draft or jump the caret
  when English, Arabic, numbers and paper IDs are mixed. Keep saved text logical.

These choices follow W3C's [document direction](https://www.w3.org/International/questions/qa-html-dir)
and [inline isolation](https://www.w3.org/International/articles/inline-bidi-markup/)
guidance. Illustrative app-authored markup, not model output:

```html
<html lang="ar-EG" dir="rtl">
  <p>خلّينا نفهم <bdi dir="ltr" lang="en">Retrieval-Augmented Generation (RAG)</bdi> خطوة بخطوة.</p>
  <p>المصدر: <bdi dir="ltr">[p4b0 / p. 4]</bdi></p>
</html>
```

Use logical layout properties (`margin-inline`, `padding-inline`, `text-align:
start`) and logical DOM order for focus/readout. Avoid reversing both CSS row
order and RTL direction. Mirror directional navigation icons only where they
represent previous/next reading; label the controls in words. Scientific edges,
axes, code, equations and original source figures keep their own semantics.
[CSS logical properties](https://www.w3.org/TR/css-logical-1/).

## Typography, wrapping and visual exports

Start the viewer with an installed Arabic/Latin-capable font, an adjustable
18 CSS-pixel body size and roughly 1.8 line height. These are product starting
values for review, not a claim of universal readability or a WCAG font-size rule.
Use comfortable paragraph spacing and avoid forced justification, manual
tatweel and added Arabic letter spacing. Preserve diacritics and joiners.

Wrap prose naturally and measure shaped text with the actual font and width in
image exports. Do not reuse character-count wrapping/truncation as a fit test.
Keep word/grapheme boundaries, combining marks and emoji sequences intact.
Use pixel bounds for each complete candidate line: summing isolated word widths
can miss kerning/shaping. Expand, paginate or provide full accessible details
instead of silently clipping scientific labels. Long URLs can wrap visually
without inserting characters into the copied URL; long code/equations get a
bounded scroll region. A multiword term may wrap at spaces if kept in one isolate.

SVG text needs its own explicit direction/isolation handling; HTML `bdi` is not
an SVG text element. Use tested application-authored `text`/`tspan` attributes
and retain a selectable HTML text alternative. Don't position Arabic glyphs
individually. [SVG text layout](https://www.w3.org/TR/SVG2/text.html).

PNG needs a shaping/bidi-capable backend. Existing Pillow/libraqm and Windows
GDI paths are candidates, not evidence of identical mixed-text output. Measure
with the chosen backend, inspect both outputs and preserve the existing missing-
shaping text fallback. Never apply pre-shaping/visual reordering a second time.
[Pillow text measurement/direction](https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html).

Actual current limitation: `src/services/study/visuals.py` uses `textwrap.wrap`
and character slices before drawing; `render_map.ps1` uses fixed rectangles.
The new visual renderer must not copy those constraints as a layout guarantee.
Changing the existing reading-map implementation requires regression checks.

## Telegram is a separate output adapter

The current bot sends ordinary `sendMessage` plain text. Do not send browser
`bdi`, `dir` or CSS as if Telegram would render a web page. The ordinary Bot API
HTML whitelist does not document `bdi`/a general `dir` control. New rich-message
APIs are a separate potential migration, outside the current delivery contract.
[Bot API formatting](https://core.telegram.org/bots/api#formatting-options).

For known inline LTR runs, qualify paired `LRI` (`U+2066`) and `PDI` (`U+2069`)
in the presentation copy; unknown inline directions may use `FSI` (`U+2068`).
Isolates are inline tools, not a cross-paragraph base-direction setting. Prefer
Arabic paragraph openings and standalone source/code/link lines for predictable
reading. Avoid routine directional overrides (`LRO`/`RLO`) and blanket RLM
insertion. [W3C plain-text isolation](https://www.w3.org/International/questions/qa-bidi-unicode-controls).

Split semantic blocks before adding presentation isolates; every delivered part
must have balanced isolates, even when a long block spans messages. Count the
inserted controls and part labels within the existing conservative UTF-16 message
budget. If entities are introduced, calculate their UTF-16 offsets against the
final emitted text, including emoji/controls. Preserve all current owner, quota,
acknowledgement and replay gates. Formatting must not admit a model job.

Qualification includes Telegram Desktop plus the owner's actual mobile client;
record client/version and screenshots. Do not promise identical client rendering
from a browser test. If an isolate case fails, use simpler separate lines and a
text alternative; don't add an inference retry. No unsolicited test messages.

## Copy, sources and unexpected formatting controls

App-created copy buttons copy canonical text without application-added invisible
marks. Test ordinary selection/copy too: HTML, SVG and Telegram may differ.
Commands, URLs and citations must remain usable; Telegram copy must not add
marks inside identifiers. Exact source copy remains explicitly identified.

Keep raw source content unchanged if it contains directional controls. Flag the
condition, contain it and offer a clearly labeled escaped view; never call a
sanitized quotation byte-identical. Reject unexpected overrides/unbalanced
controls in new generated visual labels with a bounded validation error. Do not
strip all Unicode format characters: joiners can be meaningful. The renderer
may add only its own paired controls at the last presentation boundary.

## Acceptance cases and build placement

These are UI fixtures, not extracted paper claims or benchmark results. Turn
them into shared automated fixtures during V2; inspect actual renderings in V3/
V4, and exercise the Telegram adapter during V7.

| Case | Example or construction | Required observation |
| --- | --- | --- |
| Term inside Arabic | `خلّينا نفهم Retrieval-Augmented Generation (RAG) خطوة بخطوة.` | Phrase/brackets stay together semantically; Arabic punctuation stays outside. |
| English-first explanation | `RAG هنا مجرد مصطلح في مثال للعرض.` | Teaching paragraph remains RTL; the initial term is LTR. |
| Signs and identifiers | `C++`، `BERT-base`، `top-K` | Signs/hyphens stay with the term; copy is unchanged. |
| Citation | `المصدر: [p4b0 / ص 4]` | Isolate the citation group; keep ID/page association and canonical copy. |
| Numeric teaching example | `القيمة الافتراضية: -0.25 ± 0.03 ms (95%)` | Sign/decimal/unit/parentheses keep logical order; no scientific-result claim. |
| Arabic-Indic digits | `الخطوة ٢ من ٨` | Digits remain valid; don't automatically transliterate source numbers. |
| Equation example | `p(y\|x) = sum_z p(z\|x) p(y\|x,z)` and `x < 0` | Whole expression LTR, comparisons unchanged; Arabic explanation separate. |
| Paper URL / command | `https://arxiv.org/abs/2005.11401v4`, `/deep` | Correct click/copy; controls never become part of a command/URL. |
| Unknown mixed title | English title containing an Arabic phrase, and the converse | Outer auto direction plus nested isolation; no spill into adjacent page numbers. |
| Combining/emoji boundary | Arabic diacritics and `👩🏽‍🔬` near a wrap/message boundary | No lost combining mark, broken sequence or incorrect UTF-16 offsets. |
| Hostile control | Construct `U+202E` or an unmatched `U+2066` inside a label | Generated label rejected; source preserved/flagged, adjacent content unaffected. |
| Long/narrow content | Long title, URL, quotation and multiword term | Full text reachable without horizontal scrolling of the whole reading page. |

Browser acceptance: desktop and 320 CSS-pixel reading width, 200% text resizing,
400% zoom from 1280 pixels, applicable user text-spacing overrides, keyboard and
screen-reader order, and copy/paste into a plain-text field. Two-dimensional
diagrams/tables may have their own controlled pan/scroll plus a text alternative;
do not shrink everything to fit. These are planned checks, not a claim of WCAG
conformance. [Reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html),
[text-spacing adaptability](https://www.w3.org/WAI/WCAG22/Understanding/text-spacing.html).

Direction, copying, navigation and text alternatives require zero inference and
zero new startup service/model weights. A visual failure must leave the readable
text/source and working controls available; it must not trap the learner behind
a spinner or force regeneration just to continue reading.
