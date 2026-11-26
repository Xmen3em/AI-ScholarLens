# ScholarLens static site

A dependency-free explainer for ScholarLens. Plain HTML, CSS, inline SVG and a
small optional JavaScript navigation toggle. No framework, build step, analytics,
tracking, cookies, browser storage, external fonts or third-party scripts. All
core content and diagrams work with JavaScript disabled.

## Review locally

Open `index.html` directly in a browser, or serve the `site/` directory from the
repository root:

```powershell
.venv-win/Scripts/python.exe -I -m http.server 8080 --directory site
```

Then visit `http://127.0.0.1:8080/`. This serves only local static files; stop the
server with Ctrl+C when finished. Opening `index.html` directly does not require
the server. `styles.css`, `script.js` and `favicon.svg` must stay beside it.

The page includes an illustrative chat, not a captured bot response. Its example
quote is explicitly placeholder text, not an excerpt from a paper. The main README
includes owner-supplied Telegram lesson captures, which remain separate from this
illustrative chat.

Optional local verification uses the repository's existing `websocket`
dependency and an installed Chrome/Edge browser. It starts an isolated headless
profile, opens only the local page, and writes screenshots and JSON results to an
ignored output directory. It does not contact GitHub, Cloudflare, Telegram or a
model provider.

```powershell
.venv-win/Scripts/python.exe -I tests/browser/check_document_links.py
.venv-win/Scripts/python.exe -I tests/browser/check_static_site.py --root . --output tests/test_output/site-review --browser "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

Use `--static-only` to check local links, fragments, SVG parsing and JavaScript
without starting a browser. The full check captures desktop, phone and
narrow-phone layouts, tests the optional menu and no-JavaScript navigation, and
asserts against horizontal body overflow and external HTTP requests. It does not
check external URL availability, real-device rendering or screen-reader output.

## Deploy to Cloudflare Pages (owner runs these)

From the repository root:

```bash
npx wrangler@3 login
npx wrangler@3 pages deploy site --project-name scholarlens
```

The first deployment creates the project if needed. Wrangler requires Node.js/npm,
an authenticated Cloudflare account, and permission to create the Pages project.
No environment variables or secrets belong in this directory.

Or use **Cloudflare dashboard → Workers & Pages → Create → Pages → Connect to Git**:

1. Select `Xmen3em/AI-ScholarLens`.
2. Leave the build command empty.
3. Set the build output directory to `site`.
4. Deploy. The expected address is `https://scholarlens.pages.dev` when that project
   name is available and created in your account. Verify the actual URL in Cloudflare.

The project name was chosen for this handoff, not verified against an existing
Cloudflare account. No deployment has been performed by the agent.

## Content sources

- Request graph: `src/services/study/service.py` and `src/services/study/api.py`.
- Evidence checks: `src/services/study/tutor.py`, `docs/specs/claim-check.md`.
- Access, reservations, pool and retention: `docs/specs/multi-user.md`,
  `src/services/study/access.py`, `src/services/study/pool.py` and
  `src/services/study/registry.py`.
- Route, tokenizer and bounds: `src/services/study/models.py`,
  `src/services/study/glm_tokenizer.py`, `src/services/study/tutor.py`.
- Research status: `docs/specs/study-research.md`.
- Metrics, labels and judging limitations: `evaluation/paper_benchmark/REPORT.md`.
- Dependency versions: `pyproject.toml`.

When behavior or measured results change, update the corresponding page section
and the main README. Preserve the distinction between exact-support validation
and semantic correctness, AI-delegated labels and independent human labels, and
frozen DeepInfra benchmark results and the current Fireworks route.
