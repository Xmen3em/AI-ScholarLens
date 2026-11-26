"""Local-only browser/static checks for the dependency-free explainer site.

Run from the repository root with a Chrome/Edge executable in --browser.
No network destinations other than the local DevTools browser are used.
"""

import argparse
import base64
import html.parser
import json
import os
import re
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import websocket


class Links(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.references = []
        self.in_diagram = 0
        self.node = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            self.ids.append(attributes["id"])
        for name in ("href", "src"):
            if name in attributes:
                self.references.append(attributes[name])
        if tag == "svg" and "viewBox" in attributes and "class" in attributes and "diagram" in attributes["class"]:
            self.in_diagram += 1
        elif self.in_diagram and tag in {"text", "rect", "circle"}:
            self.node.append([tag, attributes, ""])

    def handle_endtag(self, tag):
        if tag == "svg" and self.in_diagram:
            self.in_diagram -= 1

    def handle_data(self, data):
        if self.node:
            self.node[-1][2] += data


def check_static(root: Path, output: Path):
    html_text = (root / "site/index.html").read_text(encoding="utf-8")
    parser = Links()
    parser.feed(html_text)
    assert len(parser.ids) == len(set(parser.ids)), "duplicate HTML/SVG IDs"
    for ref in parser.references:
        if ref.startswith("#"):
            assert ref[1:] in parser.ids, f"missing fragment: {ref}"
        elif ref.startswith("https://github.com/Xmen3em/AI-ScholarLens"):
            path = ref.removeprefix("https://github.com/Xmen3em/AI-ScholarLens").removeprefix("/blob/master/")
            if path:
                assert (root / path).is_file(), f"missing GitHub source target: {path}"
        elif "://" not in ref:
            assert (root / "site" / ref).is_file(), f"missing local asset: {ref}"
        else:
            raise AssertionError(f"unexpected external asset/link: {ref}")
    for svg in (root / "site").glob("*.svg"):
        ET.parse(svg)
    diagrams = re.findall(r'<svg class="diagram"[\s\S]*?</svg>', html_text)
    for diagram in diagrams:
        ET.fromstring(diagram)
    script = (root / "site/script.js").read_text(encoding="utf-8")
    assert "https://" not in script and "http://" not in script
    assert not re.search(r"\b(?:fetch|XMLHttpRequest|WebSocket|sendBeacon)\b", script)
    for tag, attributes, text in parser.node:
        if tag == "text" and text.strip():
            assert "x" in attributes, f"SVG text lacks x: {text}"
        if tag == "rect":
            assert "width" in attributes and "height" in attributes
    result = {"local_links_and_fragments": len(parser.references), "unique_ids": len(parser.ids), "inline_diagrams": len(diagrams)}
    assert result["inline_diagrams"] == 4, "the four architecture diagrams must be present"
    (output / "static-checks.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


class Browser:
    def __init__(self, executable: Path, output: Path):
        profile = output / "profile"
        self.process = subprocess.Popen([
            str(executable), "--headless=new", "--remote-debugging-port=0",
            "--remote-debugging-address=127.0.0.1", "--remote-allow-origins=http://127.0.0.1",
            f"--user-data-dir={profile.resolve()}", "--no-first-run", "--no-default-browser-check",
            "--disable-background-networking", "--disable-component-update", "--disable-sync",
            "--disable-default-apps", "--disable-extensions", "--safebrowsing-disable-auto-update",
            "--host-resolver-rules=MAP * ~NOTFOUND", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.sequence = 0
        self.events: list[dict] = []
        try:
            deadline = time.monotonic() + 15
            active_port = None
            while active_port is None:
                try:
                    active_port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
                except (FileNotFoundError, PermissionError, OSError, ValueError, IndexError):
                    if time.monotonic() > deadline:
                        raise RuntimeError("browser_start_timeout") from None
                    time.sleep(.05)
            with urllib.request.urlopen(f"http://127.0.0.1:{active_port}/json/list", timeout=5) as response:
                target = next(page for page in json.load(response) if page["type"] == "page")
            self.connection = websocket.create_connection(target["webSocketDebuggerUrl"], origin="http://127.0.0.1", timeout=10)
            for method in ("Page.enable", "Runtime.enable", "Network.enable", "Log.enable"):
                self.command(method)
        except Exception:
            self.close()
            raise

    def command(self, method, params=None):
        self.sequence += 1
        self.connection.send(json.dumps({"id": self.sequence, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.connection.recv())
            if message.get("id") == self.sequence:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})
            self.events.append(message)

    def evaluate(self, expression):
        result = self.command("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        if result.get("exceptionDetails"):
            raise RuntimeError(result["exceptionDetails"])
        return result["result"].get("value")

    def viewport(self, width, height, mobile=False):
        self.command("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": mobile})

    def open(self, url):
        self.command("Page.navigate", {"url": url})
        deadline = time.monotonic() + 10
        while not self.evaluate(f"location.href==={json.dumps(url)} && document.readyState==='complete'"):
            if time.monotonic() > deadline:
                raise RuntimeError("page_load_timeout")
            time.sleep(.05)

    def check(self, width, height, name):
        self.viewport(width, height, mobile=width < 600)
        assert self.evaluate("[...document.querySelectorAll('svg.diagram')].every(svg => svg.getBoundingClientRect().width>0 && svg.parentElement.scrollWidth>=svg.getBoundingClientRect().width)")
        overflow = self.evaluate("""[...document.querySelectorAll('body *')].filter(el => {
          const r=el.getBoundingClientRect(), style=getComputedStyle(el);
          return style.position!=='fixed' && r.width>0 && (r.left < -1 || r.right > document.documentElement.clientWidth+1) && !el.closest('.diagram-scroll, .stack-table-wrap');
        }).map(el => ({tag:el.tagName,cls:el.className,left:el.getBoundingClientRect().left,right:el.getBoundingClientRect().right}))""")
        assert not overflow, f"unexpected offscreen content: {overflow}"
        assert self.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), f"horizontal body overflow: {name}"
        return self.evaluate("({width:innerWidth, clientWidth:document.documentElement.clientWidth, bodyWidth:document.documentElement.scrollWidth, sections:document.querySelectorAll('main section').length, diagrams:document.querySelectorAll('svg.diagram').length, scripts:document.scripts.length})")

    def click_menu(self):
        box = self.evaluate("(() => {const r=document.querySelector('.menu-button').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()")
        for kind in ("mousePressed", "mouseReleased"):
            self.command("Input.dispatchMouseEvent", {"type": kind, **box, "button": "left", "clickCount": 1})

    def screenshot(self, path):
        result = self.command("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        path.write_bytes(base64.b64decode(result["data"]))

    def close(self):
        if hasattr(self, "connection"):
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--static-only", action="store_true")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browser", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    static = check_static(args.root, args.output)
    print(json.dumps({"static": static}, indent=2), flush=True)
    if args.static_only:
        return
    browser = Browser(args.browser, args.output)
    try:
        results = {"static": static, "browser": args.browser.name}
        for width, height, name in [(1440, 1000, "desktop"), (390, 844, "phone"), (320, 740, "narrow-phone")]:
            url = (args.root / "site/index.html").resolve().as_uri()
            browser.open(url)
            browser.viewport(width, height, mobile=width < 600)
            browser.evaluate("scrollTo(0,0)")
            results[name] = browser.check(width, height, name)
            print(json.dumps({name: results[name]}), flush=True)
            assert results[name]["width"] == width, f"browser expanded viewport: {results[name]}"
            browser.screenshot(args.output / f"{name}-hero.png")
            if width < 600:
                browser.click_menu()
                assert browser.evaluate("document.querySelector('.menu-button').getAttribute('aria-expanded')") == "true"
                browser.click_menu()
                assert browser.evaluate("document.querySelector('.menu-button').getAttribute('aria-expanded')") == "false"
            for anchor in ("claim-check", "multiuser-heading", "routing-heading", "benchmark"):
                browser.evaluate(f"document.getElementById('{anchor}').scrollIntoView(); scrollBy(0,-85)")
                browser.screenshot(args.output / f"{name}-{anchor}.png")
        browser.command("Emulation.setScriptExecutionDisabled", {"value": True})
        browser.open((args.root / "site/index.html").resolve().as_uri())
        browser.viewport(390, 844, mobile=True)
        assert browser.evaluate("getComputedStyle(document.querySelector('#site-nav')).display") == "flex"
        assert browser.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        assert browser.evaluate("document.querySelectorAll('main section').length") == 8
        results["no_javascript"] = "navigation and full content remain available"
        failures = [event for event in browser.events if event.get("method") in ("Runtime.exceptionThrown", "Log.entryAdded")]
        network = [event for event in browser.events if event.get("method") == "Network.requestWillBeSent" and event["params"]["request"]["url"].startswith("http")]
        assert not failures, failures
        assert not network, network
        results["runtime_errors"] = failures
        results["external_http_requests"] = network
        (args.output / "browser-checks.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))
    finally:
        browser.close()


if __name__ == "__main__":
    main()
