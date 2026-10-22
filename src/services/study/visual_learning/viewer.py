"""Self-contained desktop artifact; no service, model or personal state is opened."""

import base64
import hashlib
import json
from contextlib import suppress
from html import escape
from pathlib import Path

from src.services.study.visual_learning.catalog import load_curated_method
from src.services.study.visual_learning.models import CuratedMethod, VisualError, VisualSpec
from src.services.study.visual_learning.renderer import render_png, render_svg
from src.services.study.visual_learning.text import runs_html
from src.services.study.visual_learning.validation import default_spec, validate_spec


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _csp_hash(content: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(content.encode("utf-8")).digest()).decode("ascii") + "'"


def build_viewer(spec: VisualSpec, catalog: CuratedMethod, *, png_phases: set[str]) -> str:
    spec = validate_spec(spec, catalog)
    css = Path(__file__).with_name("viewer.css").read_text(encoding="utf-8")
    script = Path(__file__).with_name("viewer.js").read_text(encoding="utf-8")
    csp = (f"default-src 'none'; script-src {_csp_hash(script)}; style-src {_csp_hash(css)}; "
           "img-src 'self' data:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'")
    embedded = json.dumps({"spec": spec.model_dump(mode="json"), "catalog": catalog.model_dump(mode="json")}, ensure_ascii=False)
    embedded = embedded.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    figures = []
    alternatives = []
    for phase, label in [("inference", "وقت الاستخدام"), ("training", "وقت التدريب")]:
        svg = render_svg(spec, catalog, phase=phase, interactive=True)
        png_link = f'<a href="{phase}.png" download>صورة PNG</a>' if phase in png_phases else '<span>الصورة غير متاحة؛ الرسم المتجهي والنص موجودين.</span>'
        hidden = " hidden" if phase == "training" else ""
        figures.append(f'<div id="figure-{phase}"{hidden}><div class="diagram-scroll" tabindex="0" '
                       f'role="region" aria-label="رسم {label}، تقدر تسحب لعرضه">{svg}</div>'
                       f'<div class="download-row"><a href="{phase}.svg" download>رسم SVG</a>{png_link}</div></div>')
        items = "".join(f'<li><h3>{escape(step.heading_ar)}</h3><p dir="rtl">{runs_html(step.body)}</p></li>'
                        for step in spec.steps if step.phase == phase)
        alternatives.append(f'<section><h2>{label}</h2><ol>{items}</ol></section>')
    sources = "".join(
        f'<article class="source-card" data-evidence="{item.id}"><h3><bdi dir="ltr">{item.block_id}</bdi>'
        f' · صفحة {item.page} · <bdi dir="auto">{escape(item.section)}</bdi></h3>'
        f'<blockquote dir="ltr" lang="en">{escape(item.quote)}</blockquote>'
        f'<a href="{spec.source.url}#page={item.page}" target="_blank" rel="noopener noreferrer">افتح الصفحة الأصلية</a></article>'
        for item in catalog.evidence)
    first = spec.steps[0]
    return f'''<!doctype html>
<html lang="ar-EG" dir="rtl">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{escape(csp, quote=True)}">
<title>ScholarLens — نفهم RAG خطوة بخطوة</title><style>{css}</style></head>
<body><a class="skip-link" href="#lesson">انتقل للشرح</a>
<header class="topbar"><div class="bar-inner"><div class="brand"><bdi dir="ltr">ScholarLens</bdi>
<small>مساحة لفهم الأبحاث</small></div><span class="local-badge">نموذج محلي مُراجع</span></div></header>
<main><section class="intro"><p class="eyebrow">الورقة / فهم الطريقة</p><h1>{escape(spec.title_ar)}</h1>
<p class="paper-title" lang="en" dir="ltr">{escape(spec.source.title)}</p>
<div class="source-meta"><bdi dir="ltr">arXiv: {spec.source.paper_id}</bdi><span>المصدر: الصفحات <bdi dir="ltr">٢–٤</bdi></span>
<a href="{spec.source.url}" target="_blank" rel="noopener noreferrer">الورقة الأصلية</a></div>
<p class="notice">{escape(catalog.scope_notice)}</p></section>
<p id="visual-error" class="error-notice" hidden>التفاعل ما اشتغلش. الشرح النصي والمراجع موجودين تحت، وتقدر تفتح الرسوم المحفوظة.</p>
<noscript><p class="error-notice">التفاعل محتاج JavaScript. كل الخطوات والمصادر موجودة في الشرح النصي تحت.</p></noscript>
<div class="phase-controls" role="group" aria-label="مرحلة الطريقة">
<button type="button" data-phase="inference" aria-pressed="true">وقت الاستخدام</button>
<button type="button" data-phase="training" aria-pressed="false">وقت التدريب</button></div>
<div class="workspace"><article id="lesson" class="lesson-panel" aria-label="شرح الخطوة">
<p id="step-counter" class="step-counter">الخطوة ١ من ٤</p>
<div aria-live="polite" aria-atomic="true"><h2 id="step-heading">{escape(first.heading_ar)}</h2>
<p id="step-body" class="step-copy" dir="rtl">{runs_html(first.body)}</p></div>
<ol id="step-list" class="steps" aria-label="خطوات الشرح"></ol>
<nav class="navigation" aria-label="التنقل بين الخطوات"><button id="previous" type="button" disabled>السابق</button>
<button id="next" type="button">التالي</button></nav>
<div class="small-actions"><button id="show-source" type="button">شوف الدليل</button>
<button id="copy-step" type="button">نسخ الشرح</button></div>
<p id="status" class="status" role="status"></p><textarea id="copy-field" class="copy-field" dir="auto" readonly hidden aria-label="النص الجاهز للنسخ"></textarea>
<div class="component-area"><label for="component-picker">إيه دور المكوّن ده؟</label>
<select id="component-picker"><option value="">اختار مكوّن من الرسم</option></select>
<p id="component-details" dir="rtl">تفاصيل المكوّن هتظهر هنا.</p></div>
<details class="quick-check"><summary>سؤال للمراجعة الذاتية</summary>
<p>في التدريب، إيه الجزئين اللي أوزانهم بتتحدّث؟ راجع الأسهم البرتقالي والأجزاء المكتوب عليها ثابت، وبعدها افتح الدليل.</p></details>
</article><section class="figure-panel" aria-labelledby="diagram-heading">
<div class="figure-heading"><h2 id="diagram-heading">الطريقة قدامك</h2><p>اضغط على أي مكوّن عشان تفحصه</p></div>
{''.join(figures)}<p class="caption">السهم له معنى محدد: انتقال داتا، تجهيز مسبق، أو تحديث أوزان. اتجاه الواجهة ما بيغيّرش معناه.</p>
</section></div>
<details id="evidence-panel" class="source-panel"><summary id="evidence-summary">الدليل الأصلي · <span id="evidence-count">المراجع القصيرة</span></summary>
<p class="notice">المقتطفات دي علامات للوصول للمكان. راجع الصفحة كاملة للسياق؛ الشرح العربي إعادة صياغة، مش اقتباس حرفي.</p>{sources}</details>
<details id="text-alternative" class="text-panel"><summary>كل الشرح كنص، من غير الاعتماد على الرسم</summary>{''.join(alternatives)}</details>
</main><footer class="page-footer">التنقل وفحص المكوّنات محليين. نموذج لورقة واحدة؛ دعم أي ورقة والتكامل مع Telegram ليهم مراحل منفصلة.</footer>
<script id="visual-data" type="application/json">{embedded}</script><script>{script}</script></body></html>'''


def export_demo(output: Path) -> dict:
    if output.exists() or output.is_symlink():
        raise VisualError("output_exists")
    catalog = load_curated_method()
    spec = default_spec(catalog)
    assets = {"visual-spec.json": (spec.model_dump_json(indent=2) + "\n").encode("utf-8")}
    png_phases = set()
    for phase in ["inference", "training"]:
        assets[phase + ".svg"] = render_svg(spec, catalog, phase=phase).encode("utf-8")
        raster = render_png(spec, catalog, phase=phase)
        if raster is not None:
            assets[phase + ".png"] = raster
            png_phases.add(phase)
    assets["index.html"] = build_viewer(spec, catalog, png_phases=png_phases).encode("utf-8")
    manifest = {"schema_version": 1, "scope": "curated_offline_fixture", "source_sha256": spec.source.sha256,
                "catalog_revision": catalog.revision, "png_phases": sorted(png_phases),
                "assets": {name: _digest(content) for name, content in assets.items()}}
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise VisualError("output_exists") from None
    created = []
    try:
        for name, content in assets.items():
            path = output / name
            with path.open("xb") as stream:
                created.append(path)
                stream.write(content)
        path = output / "manifest.json"
        with path.open("x", encoding="utf-8") as stream:
            created.append(path)
            stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    except OSError:
        for path in created:
            with suppress(OSError):
                path.unlink(missing_ok=True)
        with suppress(OSError):
            output.rmdir()
        raise VisualError("export_write_failed") from None
    return manifest
