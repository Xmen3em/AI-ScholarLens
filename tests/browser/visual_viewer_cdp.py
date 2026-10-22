"""Verify the public offline viewer in a fresh installed Chrome profile.

Run explicitly with --viewer and a new --output directory. Uses the existing
locked websocket-client development dependency, no personal browser profile.
"""

import argparse
import base64
import json
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path

import websocket
from pydantic import ValidationError
from src.services.study.visual_learning.catalog import load_curated_method
from src.services.study.visual_learning.models import TextRun
from src.services.study.visual_learning.text import runs_html
from src.services.study.visual_learning.validation import default_spec
from src.services.study.visual_learning.viewer import build_viewer


class Browser:
    def __init__(self, output: Path):
        chrome = next((path for path in [Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
                                         Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")]
                       if path.is_file()), None)
        if chrome is None:
            raise RuntimeError("installed_test_browser_required")
        profile = output / "anonymous-browser-profile"
        profile.mkdir()
        self.process = subprocess.Popen([str(chrome), "--headless=new", "--remote-debugging-port=0",
                                         "--remote-debugging-address=127.0.0.1", "--remote-allow-origins=http://127.0.0.1",
                                         "--user-data-dir=" + str(profile.resolve()), "--no-first-run",
                                         "--no-default-browser-check", "--disable-background-networking",
                                         "--disable-sync", "--disable-extensions", "about:blank"],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.events: list[dict] = []
        self.sequence = 0
        self.connection = None
        try:
            self.connect(profile)
        except Exception:
            self.close()
            raise

    def connect(self, profile: Path):
        deadline = time.monotonic() + 15
        while not (profile / "DevToolsActivePort").exists():
            if time.monotonic() > deadline:
                raise RuntimeError("browser_start_timeout")
            time.sleep(.05)
        port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as response:
            target = next(page for page in json.load(response) if page["type"] == "page")
        self.connection = websocket.create_connection(target["webSocketDebuggerUrl"], origin="http://127.0.0.1", timeout=10)
        for method in ["Page.enable", "Runtime.enable", "Log.enable", "Network.enable", "DOM.enable", "CSS.enable"]:
            self.command(method)
        self.command("Emulation.setDeviceMetricsOverride", {"width": 1400, "height": 1100, "deviceScaleFactor": 1, "mobile": False})
        self.version = self.command("Browser.getVersion")["product"]

    def command(self, method: str, params: dict | None = None) -> dict:
        self.sequence += 1
        self.connection.send(json.dumps({"id": self.sequence, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.connection.recv())
            if message.get("id") == self.sequence:
                if "error" in message:
                    raise RuntimeError({"method": method, "error": message["error"]})
                return message.get("result", {})
            self.events.append(message)

    def evaluate(self, expression: str):
        result = self.command("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        if result.get("exceptionDetails"):
            raise RuntimeError("browser_evaluation_failed")
        return result["result"].get("value")

    def open(self, path: Path):
        url = path.resolve().as_uri()
        self.command("Page.navigate", {"url": url})
        deadline = time.monotonic() + 10
        while not self.evaluate(f"location.href==={json.dumps(url)} && document.readyState==='complete'"):
            if time.monotonic() > deadline:
                raise RuntimeError("page_load_timeout")
            time.sleep(.05)

    def scroll_into_view(self, selector: str):
        root = self.command("DOM.getDocument")["root"]["nodeId"]
        node = self.command("DOM.querySelector", {"nodeId": root, "selector": selector})["nodeId"]
        self.command("DOM.scrollIntoViewIfNeeded", {"nodeId": node})

    def click(self, selector: str):
        self.scroll_into_view(selector)
        rect = self.evaluate(f"(() => {{ const r=document.querySelector({json.dumps(selector)}).getBoundingClientRect(); return {{x:r.x+r.width/2,y:r.y+r.height/2}}; }})()")
        for action in ["mousePressed", "mouseReleased"]:
            self.command("Input.dispatchMouseEvent", {"type": action, **rect, "button": "left", "clickCount": 1})

    def key(self, key: str, code: int):
        for action in ["keyDown", "keyUp"]:
            self.command("Input.dispatchKeyEvent", {"type": action, "key": key, "windowsVirtualKeyCode": code})

    def screenshot(self, path: Path):
        # Capture actual viewports. Chrome 155's beyond-viewport capture shifts
        # some RTL pages despite correct DOM bounds; inspect sections separately.
        result = self.command("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        path.write_bytes(base64.b64decode(result["data"]))

    def close(self):
        if self.connection is not None:
            try:
                self.command("Browser.close")
            except (OSError, RuntimeError, websocket.WebSocketException):
                pass
            self.connection.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)


def check_viewer(browser: Browser, viewer: Path, output: Path) -> dict:
    browser.open(viewer)
    assert browser.evaluate("document.querySelectorAll('#step-list button').length") == 4
    assert browser.evaluate("document.getElementById('visual-error').hidden")
    assert browser.evaluate("getComputedStyle(document.getElementById('step-body')).direction") == "rtl"
    browser.screenshot(output / "desktop-inference.png")
    browser.click("#next")
    assert browser.evaluate("document.getElementById('previous').disabled") is False
    browser.click("#step-list li:nth-child(3) button")
    assert browser.evaluate("document.activeElement === document.querySelector('#step-list li:nth-child(3) button')")
    browser.key("Enter", 13)
    assert browser.evaluate("document.getElementById('step-counter').textContent") == "الخطوة ٣ من ٤"
    browser.click('[data-phase="training"]')
    browser.click('#figure-training [data-node="document_encoder"]')
    assert browser.evaluate("document.getElementById('component-picker').value") == "document_encoder"
    assert "ثابتة" in browser.evaluate("document.getElementById('component-details').textContent")
    browser.key(" ", 32)
    assert browser.evaluate("document.getElementById('component-picker').value") == "document_encoder"
    # Browser text metrics check the real fonts, not just character counts.
    assert browser.evaluate("""[...document.querySelectorAll('#figure-training .scene-node')].every(node => {
      const box = node.querySelector('rect').getBBox();
      return [...node.querySelectorAll('text')].every(text => {
        const r=text.getBBox(); return r.x>=box.x && r.x+r.width<=box.x+box.width && r.y>=box.y && r.y+r.height<=box.y+box.height;
      });
    })""")
    browser.click("#show-source")
    assert browser.evaluate("document.getElementById('evidence-panel').open")
    browser.click("#step-list li:nth-child(4) button")
    assert browser.evaluate("document.getElementById('next').disabled")
    browser.screenshot(output / "desktop-training.png")
    tree = browser.command("Accessibility.getFullAXTree")["nodes"]
    buttons = [node for node in tree if not node.get("ignored") and node.get("role", {}).get("value") == "button"]
    assert buttons and all(node.get("name", {}).get("value") for node in buttons)

    # Deny clipboard permission in this isolated test profile: test the copy
    # fallback without reading or replacing the user's operating-system clipboard.
    browser.command("Browser.setPermission", {"permission": {"name": "clipboard-write"}, "setting": "denied"})
    browser.click("#copy-step")
    expected = browser.evaluate("JSON.parse(document.getElementById('visual-data').textContent).spec.steps[7].body.map(r=>r.text).join('')")
    deadline = time.monotonic() + 4
    while not browser.evaluate("document.getElementById('status').textContent"):
        if time.monotonic() > deadline:
            raise RuntimeError("clipboard_feedback_timeout")
        time.sleep(.05)
    assert browser.evaluate("document.getElementById('copy-field').value") == expected
    assert not browser.evaluate("document.getElementById('copy-field').hidden")

    widths = []
    for width in [1400, 1024, 768, 320]:
        browser.command("Emulation.setDeviceMetricsOverride", {"width": width, "height": 1000, "deviceScaleFactor": 1, "mobile": False})
        actual = browser.evaluate("({viewport:innerWidth,content:document.documentElement.scrollWidth})")
        assert actual["content"] <= actual["viewport"], actual
        assert_reading_bounds(browser)
        widths.append(actual)
    browser.scroll_into_view("header")
    browser.screenshot(output / "mobile-training.png")
    browser.scroll_into_view("#figure-training")
    browser.screenshot(output / "mobile-diagram.png")
    frame = browser.command("Page.getFrameTree")["frameTree"]["frame"]["id"]
    sheet = browser.command("CSS.createStyleSheet", {"frameId": frame})["styleSheetId"]
    browser.command("CSS.setStyleSheetText", {"styleSheetId": sheet, "text": ":root{font-size:36px!important}p{line-height:1.5!important;margin-block-end:2em!important;word-spacing:.16em!important}[lang=en]{letter-spacing:.12em!important}"})
    assert browser.evaluate("document.documentElement.scrollWidth<=innerWidth")
    assert_reading_bounds(browser)
    browser.scroll_into_view("#lesson")
    browser.screenshot(output / "mobile-enlarged.png")
    browser.command("CSS.setStyleSheetText", {"styleSheetId": sheet, "text": ""})
    browser.command("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]})
    assert browser.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")

    browser.command("Emulation.setDeviceMetricsOverride", {"width": 1400, "height": 1100, "deviceScaleFactor": 1, "mobile": False})
    browser.click('[data-phase="inference"]')
    samples = []
    for index in range(100):
        start = browser.evaluate("performance.now()")
        browser.click("#next" if index % 2 == 0 else "#previous")
        finish = browser.evaluate("performance.now()")
        samples.append(finish - start)
    return {"layout_widths": widths, "accessible_named_buttons": len(buttons), "copy_fallback_preserves_text": True,
            "navigation_samples": len(samples), "navigation_p95_ms": round(sorted(samples)[94], 2),
            "text_resize": "200 percent plus applicable spacing at 320 CSS pixels", "keyboard_focus_preserved": True}


def assert_reading_bounds(browser: Browser):
    assert browser.evaluate("""[...document.querySelectorAll('main, .intro, .lesson-panel, .text-panel, .source-panel, .paper-title, .step-copy')]
      .filter(e=>e.getClientRects().length).every(e=>{const r=e.getBoundingClientRect();
      return r.left>=-1 && r.right<=document.documentElement.clientWidth+1;})""")


def check_fallbacks(browser: Browser, viewer: Path, output: Path):
    html = viewer.read_text(encoding="utf-8")
    for name, content in [
        ("missing-diagram", re.sub(r"<svg\b.*?</svg>", "", html, flags=re.S)),
        ("invalid-data", re.sub(r'(<script id="visual-data" type="application/json">).*?(</script>)', r'\1invalid-json\2', html, flags=re.S)),
    ]:
        path = output / (name + ".html")
        path.write_text(content, encoding="utf-8")
        browser.open(path)
        assert not browser.evaluate("document.getElementById('visual-error').hidden")
        assert browser.evaluate("document.getElementById('text-alternative').open")
        assert browser.evaluate("document.querySelectorAll('#text-alternative li').length") == 8
        if name == "missing-diagram":
            assert not browser.evaluate("document.getElementById('next').disabled")
            browser.click("#next")
            assert browser.evaluate("document.getElementById('step-counter').textContent") == "الخطوة ٢ من ٤"
            browser.click('[data-phase="training"]')
            assert browser.evaluate("document.getElementById('step-counter').textContent") == "الخطوة ١ من ٤"
            browser.click("#show-source")
            assert browser.evaluate("document.getElementById('evidence-panel').open")
        else:
            assert browser.evaluate("document.getElementById('next').disabled")
            assert browser.evaluate("document.getElementById('evidence-panel').open")
    catalog = load_curated_method()
    catalog = catalog.model_copy(update={"source": catalog.source.model_copy(update={"title": '</script><img src="https://invalid.example/x" onerror="alert(1)">'})})
    path = output / "inert-title.html"
    path.write_text(build_viewer(default_spec(catalog), catalog, png_phases=set()), encoding="utf-8")
    browser.open(path)
    assert browser.evaluate("document.images.length") == 0


def check_reading_cases(browser: Browser, output: Path) -> int:
    root = Path(__file__).resolve().parents[2]
    cases = json.loads((root / "evaluation/visual_learning/arabic-reading.v1.json").read_text(encoding="utf-8"))["cases"]
    paragraphs = []
    expected = {}
    for case in cases:
        try:
            runs = [TextRun.model_validate(run) for run in case["runs"]]
        except ValidationError:
            assert case.get("reject")
            continue
        expected[case["id"]] = "".join(run.text for run in runs)
        paragraphs.append(f'<p id="{case["id"]}" dir="rtl">{runs_html(runs)}</p>')
    css = (root / "src/services/study/visual_learning/viewer.css").read_text(encoding="utf-8")
    path = output / "reading-cases.html"
    path.write_text('<!doctype html><html lang="ar-EG" dir="rtl"><meta charset="utf-8"><style>' + css +
                    '</style><main><section class="text-panel">' + "".join(paragraphs) + '</section></main></html>', encoding="utf-8")
    browser.open(path)
    for key, value in expected.items():
        assert browser.evaluate(f"document.getElementById({json.dumps(key)}).textContent") == value
    browser.command("Emulation.setDeviceMetricsOverride", {"width": 320, "height": 1100, "deviceScaleFactor": 1, "mobile": False})
    assert browser.evaluate("document.documentElement.scrollWidth<=innerWidth")
    assert_reading_bounds(browser)
    browser.screenshot(output / "reading-cases-mobile.png")
    return len(cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--viewer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    browser = Browser(args.output)
    result = {}
    try:
        result = check_viewer(browser, args.viewer, args.output)
        check_fallbacks(browser, args.viewer, args.output)
        result["reading_cases"] = check_reading_cases(browser, args.output)
        errors = [event for event in browser.events if event.get("method") == "Runtime.exceptionThrown"
                  or (event.get("method") == "Log.entryAdded" and event["params"]["entry"]["level"] in {"error", "warning"})]
        requests = [event["params"]["request"]["url"] for event in browser.events if event.get("method") == "Network.requestWillBeSent"]
        result.update({"browser": browser.version, "console_errors_warnings": errors,
                       "http_requests": [url for url in requests if url.startswith(("http:", "https:"))],
                       "fallbacks_checked": ["missing_diagram", "invalid_data", "inert_title"]})
        assert not errors and not result["http_requests"], result
        (args.output / "result.json").write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=True))
    finally:
        browser.close()


if __name__ == "__main__":
    main()
