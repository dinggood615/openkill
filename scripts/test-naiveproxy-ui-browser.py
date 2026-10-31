#!/usr/bin/env python3
"""Exercise the independent NaiveProxy card in a real local browser.

The LuCI endpoints are replaced only at the HTTP boundary.  The page body,
dialog script and final OpenKill CSS are the production files, so this catches
the nested-form and HTML-as-JSON regressions without contacting a router.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import re
import tempfile
import threading
from urllib.parse import parse_qs


ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / "luci-app-openkill/luasrc/view/openkill/naive_compatibility.htm"
OC_CSS = ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/oc.css"
FLAT_CSS = ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/flat.css"


def rendered_view() -> str:
    source = VIEW.read_text(encoding="utf-8")
    source = re.sub(r"<%.*?%>", "", source, flags=re.DOTALL)
    source = source.replace('data-naive-standalone-url=""', 'data-naive-standalone-url="/naive-status"')
    source = source.replace('data-naive-control-url=""', 'data-naive-control-url="/naive-control"')
    return """<!doctype html><html><head><meta charset=\"utf-8\"><script>window.L={env:{token:'fixture-token'}};</script><style>""" + OC_CSS.read_text(encoding="utf-8") + "\n" + FLAT_CSS.read_text(encoding="utf-8") + "</style></head><body><main id=\"cbi-openkill\" class=\"openkill-settings openkill-page\"><form id=\"settings-cbi-form\">" + source + "<button id=\"settings-commit\" type=\"submit\">Commit Settings</button></form></main></body></html>"


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("OPENKILL_ENVIRONMENT_LIMIT=PLAYWRIGHT_UNAVAILABLE")
        return 0

    state = {"name": "Fixture", "generation": 1, "node_state": "running", "managed": "0", "managed_group": "", "operations": [],
             "groups_state": "available", "fail_add_reason": ""}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            return

        def response(self, status: int, content_type: str, body: str) -> None:
            raw = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/", "/index.html"):
                self.response(200, "text/html; charset=utf-8", rendered_view())
                return
            if self.path.startswith("/naive-status"):
                if "operation=groups" in self.path:
                    groups = ["Main", "Backup auto"] if state["groups_state"] == "available" else []
                    self.response(200, "application/json; charset=utf-8", json.dumps({
                        "ok": state["groups_state"] != "unavailable",
                        "state": state["groups_state"],
                        "reason": {"available": "available", "empty": "no-supported-groups",
                                   "unavailable": "runtime-yaml-invalid"}[state["groups_state"]],
                        "groups": groups,
                    }))
                    return
                if "operation=yaml" in self.path:
                    self.response(200, "text/plain; charset=utf-8", '- name: "Fixture"\n  type: socks5\n  server: 127.0.0.1\n  port: 11080\n  udp: false\n')
                    return
                payload = {"updated": 1, "component_status": "available", "component_version": "fixture", "component": "/etc/naiveproxy/naive", "component_asset": "fixture", "component_machine": "x86_64", "component_reason": "available", "groups": ["Main", "Backup auto"], "nodes": {"node-fixture": {"name": state["name"], "enabled": "1", "port": "11080", "state": state["node_state"], "local_ready": "1", "health": "available", "latency_ms": "123", "checked_at": "1", "generation": str(state["generation"]), "pending_apply": "0", "managed": state["managed"], "managed_group": state["managed_group"]}}}
                self.response(200, "application/json; charset=utf-8", json.dumps(payload))
                return
            self.response(404, "text/plain", "not found")

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/naive-control" or self.headers.get("X-Requested-With") != "XMLHttpRequest":
                self.response(403, "application/json", '{"ok":false,"stage":"request","error":"forbidden"}')
                return
            length = int(self.headers.get("Content-Length", "0"))
            fields = {key: values[-1] for key, values in parse_qs(self.rfile.read(length).decode("utf-8")).items()}
            if fields.get("token") != "fixture-token":
                self.response(403, "application/json", '{"ok":false,"stage":"request","error":"missing-token"}')
                return
            operation = fields.get("operation", "")
            state["operations"].append(operation)
            if operation == "get":
                payload = {"ok": True, "stage": "node-read", "id": "node-fixture", "node": {"name": state["name"], "server": "fixture.example.test", "port": 443, "username": "fixture-user", "transport": "https", "enabled": "1", "generation": state["generation"], "password_set": True}}
            elif operation in ("import", "add"):
                if state["fail_add_reason"]:
                    self.response(422, "application/json; charset=utf-8", json.dumps({
                        "ok": False, "stage": "node-save-failed", "reason": state["fail_add_reason"],
                        "rc": 13, "detail": "standalone-bridge-returned-nonzero",
                    }))
                    return
                state["name"] = "Imported"
                payload = {"ok": True, "stage": "accepted", "id": "node-fixture"}
            elif operation == "edit":
                state["name"] = fields.get("name", state["name"])
                state["generation"] += 1
                payload = {"ok": True, "stage": "node-saved", "id": "node-fixture"}
            elif operation == "managed":
                state["managed"] = fields.get("enabled", "0")
                state["managed_group"] = fields.get("group", "") if state["managed"] == "1" else ""
                payload = {"ok": True, "stage": "managed-selection-saved", "id": "node-fixture"}
            elif operation == "start":
                state["node_state"] = "running"
                payload = {"ok": True, "stage": "service-started", "id": fields.get("id", "")}
            elif operation == "stop":
                state["node_state"] = "stopped"
                payload = {"ok": True, "stage": "service-stopped", "id": fields.get("id", "")}
            elif operation in ("component", "install", "update"):
                payload = {"ok": True, "stage": "component-candidate-ready", "candidate_version": "fixture", "asset": "fixture"}
            else:
                payload = {"ok": True, "stage": "accepted", "id": "node-fixture"}
            self.response(200, "application/json; charset=utf-8", json.dumps(payload))

    with tempfile.TemporaryDirectory(prefix="openkill-naive-ui-") as temp:
        page_file = Path(temp) / "index.html"
        page_file.write_text(rendered_view(), encoding="utf-8")
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                candidates = [Path(playwright.chromium.executable_path), Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"), Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")]
                candidates = [candidate for candidate in candidates if candidate.is_file()]
                if not candidates:
                    print("OPENKILL_ENVIRONMENT_LIMIT=PLAYWRIGHT_BROWSER_UNAVAILABLE")
                    return 0
                browser = None
                launch_errors = []
                for executable in candidates:
                    try:
                        browser = playwright.chromium.launch(headless=True, executable_path=str(executable))
                        break
                    except Exception as error:
                        launch_errors.append(type(error).__name__)
                if browser is None:
                    print("OPENKILL_ENVIRONMENT_LIMIT=PLAYWRIGHT_BROWSER_LAUNCH_UNAVAILABLE:" + ",".join(launch_errors))
                    return 0
                try:
                    page = browser.new_page(viewport={"width": 1366, "height": 900})
                    page.goto(f"http://127.0.0.1:{server.server_port}/index.html", wait_until="networkidle")
                    assert page.evaluate("document.getElementById('settings-cbi-form').checkValidity()"), "hidden Naive dialog blocked outer CBI form validation"
                    assert "2 个可用策略组" in page.locator('[data-naive-groups-status]').inner_text()
                    assert page.locator('[data-naive-action="update"]').is_visible()
                    assert page.locator('[data-naive-action="update"]').inner_text() == "安装 / 更新组件"
                    assert page.locator('.openkill-naive-more-operations').evaluate('(element) => !element.open')
                    assert page.locator('[data-naive-node-toggle="node-fixture"]').get_attribute('data-naive-operation') == "stop"
                    assert page.locator('[data-naive-node-edit="node-fixture"]').is_visible()
                    assert page.locator('[data-naive-save-start]').count() == 0
                    page.locator('[data-naive-action="import"]').click()
                    page.locator('[name="share"]').fill("naive+https://fixture-user:fixture-secret@fixture.example.test:443?security=tls&type=tcp&headerType=none#Imported")
                    page.locator('[data-naive-parse-link]').click()
                    assert page.locator('[name="name"]').input_value() == "Imported"
                    assert page.locator('[name="share"]').input_value() == "", "parsed share text must be cleared"
                    assert page.locator('[data-naive-import-start]').is_hidden(), "parsed share input should no longer be active"
                    state["fail_add_reason"] = "duplicate-node-endpoint"
                    page.locator('[data-naive-save]').click()
                    page.wait_for_function("() => document.querySelector('[data-naive-preview]')?.textContent.includes('该连接已保存')")
                    page.wait_for_function("() => document.querySelector('[data-naive-standalone-status]')?.textContent.includes('节点保存失败')")
                    assert "fixture-secret" not in page.locator('[data-naive-standalone-status]').inner_text()
                    state["fail_add_reason"] = ""
                    page.locator('[data-naive-save]').click()
                    page.wait_for_timeout(50)
                    assert state["operations"].count("start") == 0, "saving a node must not start it implicitly"
                    page.locator('[data-naive-node-edit="node-fixture"]').click()
                    assert page.locator('[name="name"]').input_value() == "Imported"
                    page.wait_for_function("() => document.querySelector('[name=\\\"password_mode\\\"]') && document.querySelector('[name=\\\"password_mode\\\"]').checked")
                    assert page.locator('[name="password_mode"]').is_checked()
                    assert page.locator('[name="password"]').input_value() == ""
                    page.locator('[name="name"]').fill("Renamed")
                    page.locator('[data-naive-save]').click()
                    page.wait_for_timeout(50)
                    assert state["operations"].count("add") >= 2 and "get" in state["operations"] and "edit" in state["operations"]
                    page.locator('[data-naive-managed-group="node-fixture"]').select_option("Main")
                    assert page.locator('[data-naive-managed="node-fixture"]').locator('xpath=..').get_attribute('class') == "openkill-naive-managed-controls"
                    page.locator('[data-naive-managed="node-fixture"]').click()
                    page.wait_for_function("() => document.querySelector('[data-naive-managed]')?.getAttribute('data-naive-managed-value') === '0'")
                    assert state["managed"] == "1"
                    assert state["managed_group"] == "Main"
                    assert "Main" in page.locator("[data-naive-standalone-rows]").inner_text()
                    page.locator('[data-naive-managed="node-fixture"]').click()
                    page.wait_for_function("() => document.querySelector('[data-naive-managed]')?.getAttribute('data-naive-managed-value') === '1'")
                    assert state["managed"] == "0"
                    page.locator('[data-naive-node-toggle="node-fixture"]').click()
                    page.wait_for_function("() => document.querySelector('[data-naive-node-toggle]')?.getAttribute('data-naive-operation') === 'start'")
                    assert state["node_state"] == "stopped"
                    page.locator('[data-naive-node-toggle="node-fixture"]').click()
                    page.wait_for_function("() => document.querySelector('[data-naive-node-toggle]')?.getAttribute('data-naive-operation') === 'stop'")
                    assert state["node_state"] == "running"
                    page.locator('.openkill-naive-row-more > summary').click()
                    page.locator('[data-naive-node-restart="node-fixture"]').click()
                    page.wait_for_timeout(50)
                    assert state["node_state"] == "running"
                    assert state["operations"].count("stop") >= 2 and state["operations"].count("start") >= 2
                    state["groups_state"] = "unavailable"
                    page.locator('[data-naive-action="refresh"]').click()
                    page.wait_for_function("() => document.querySelector('[data-naive-groups-status]')?.textContent.includes('无法解析')")
                    assert page.locator('[data-naive-managed-group="node-fixture"]').is_disabled()
                    state["groups_state"] = "empty"
                    page.locator('[data-naive-action="refresh"]').click()
                    page.wait_for_function("() => document.querySelector('[data-naive-groups-status]')?.textContent.includes('没有支持接入的策略组')")
                    assert page.locator('[data-naive-managed-group="node-fixture"]').is_disabled()
                    overflow = page.evaluate("""() => [...document.querySelectorAll('*')].filter(e => e.getBoundingClientRect().right > window.innerWidth + 1).map(e => ({tag:e.tagName, cls:e.className, right:Math.round(e.getBoundingClientRect().right)})).slice(0, 8)""")
                    assert not overflow, overflow
                    page.set_viewport_size({"width": 390, "height": 844})
                    overflow = page.evaluate("""() => [...document.querySelectorAll('*')].filter(e => e.getBoundingClientRect().right > window.innerWidth + 1).map(e => ({tag:e.tagName, cls:e.className, right:Math.round(e.getBoundingClientRect().right)})).slice(0, 8)""")
                    assert not overflow, overflow
                finally:
                    browser.close()
        finally:
            server.shutdown()
            thread.join(timeout=5)
    print("NAIVEPROXY_UI_BROWSER=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
