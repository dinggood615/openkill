#!/usr/bin/env python3
"""Run the local status preview through a real browser.

The page is built from the production status template, CSS and settings
coordinator.  Only the backend responses are mocked; the browser never opens
an external URL or contacts a router.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
PREVIEW_BUILDER = ROOT / "scripts/build-ui-preview.py"
EVIDENCE_DIR = ROOT / "artifacts/test-evidence/ui-preview"


def load_builder():
    import importlib.util

    spec = importlib.util.spec_from_file_location("openkill_preview_builder", PREVIEW_BUILDER)
    if not spec or not spec.loader:
        raise RuntimeError("PREVIEW_BUILDER_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("OPENKILL_ENVIRONMENT_LIMIT=PLAYWRIGHT_UNAVAILABLE")
        return 0

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    requests: list[str] = []
    with tempfile.TemporaryDirectory(prefix="openkill-ui-browser-") as temp:
        preview_dir = Path(temp) / "preview"
        preview = load_builder().build_preview(preview_dir)

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
                path = unquote(urlparse(self.path).path)
                requests.append(path)
                if path in ("/", "/index.html"):
                    target = preview
                elif path.startswith("/luci-app-openkill/"):
                    target = ROOT / "luci-app-openkill" / path.removeprefix("/luci-app-openkill/")
                else:
                    self.send_error(404)
                    return
                if not target.is_file():
                    self.send_error(404)
                    return
                body = target.read_bytes()
                content_types = {
                    ".html": "text/html; charset=utf-8",
                    ".css": "text/css; charset=utf-8",
                    ".js": "application/javascript; charset=utf-8",
                    ".png": "image/png",
                    ".svg": "image/svg+xml",
                    ".woff": "font/woff",
                    ".woff2": "font/woff2",
                }
                self.send_response(200)
                self.send_header("Content-Type", content_types.get(target.suffix.lower(), "application/octet-stream"))
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        browser = None
        try:
            with sync_playwright() as playwright:
                executable = Path(playwright.chromium.executable_path)
                if not executable.is_file():
                    candidates = (
                        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
                        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
                        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
                    )
                    executable = next((path for path in candidates if path.is_file()), Path())
                if not executable.is_file():
                    print("OPENKILL_ENVIRONMENT_LIMIT=PLAYWRIGHT_BROWSER_UNAVAILABLE")
                    return 0
                try:
                    browser = playwright.chromium.launch(headless=True, executable_path=str(executable))
                except Exception as error:  # launch is an environment boundary
                    print(f"UI_BROWSER=FAIL\nPLAYWRIGHT_LAUNCH_ERROR={type(error).__name__}")
                    return 1
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                console_errors: list[str] = []
                page_errors: list[str] = []
                blocked_requests: list[str] = []
                page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(str(error)))

                def route_handler(route):
                    url = route.request.url
                    parsed = urlparse(url)
                    if parsed.scheme in ("http", "https") and parsed.hostname not in ("127.0.0.1", "localhost"):
                        blocked_requests.append(url)
                        route.abort()
                    else:
                        route.continue_()

                page.route("**/*", route_handler)
                page.goto(f"http://127.0.0.1:{server.server_port}/index.html", wait_until="networkidle", timeout=30_000)

                probe = page.evaluate(
                    """
                    async () => {
                      const manager = window.openkillPreview && window.openkillPreview.settings;
                      if (!manager) throw new Error('PRODUCTION_SETTINGS_MANAGER_MISSING');
                      manager.responseSettleDelay = 0;
                      manager.confirmationTimeout = 80;
                      manager.setControls('rule_mode', 'rule', false);
                      window.switch_rule_mode('global');
                      const staleRejected = !manager.shouldApplyPoll('rule_mode', 'rule');
                      const optimistic = document.querySelector('input[name="radios"]:checked')?.value === 'global';
                      await new Promise(resolve => setTimeout(resolve, 20));
                      const confirmed = document.querySelector('input[name="radios"]:checked')?.value === 'global';
                      const staleAfterResponseRejected = !manager.shouldApplyPoll('rule_mode', 'rule');
                      const matchingPollAccepted = manager.shouldApplyPoll('rule_mode', 'global');
                      manager.setControls('run_mode', 'future-mode', false);
                      const unknownRunModeCleared = document.querySelectorAll('input[name="radios-ru"]:checked').length === 0;
                      manager.setControls('run_mode', '-tun', false);
                      manager.setControls('rule_mode', 'rule', false);
                      manager.confirmedValues.rule_mode = 'rule';
                      const originalGet = window.XHR.get;
                      window.XHR.get = (endpoint, params, callback) => callback({status: 503}, {});
                      window.switch_rule_mode('global');
                      await new Promise(resolve => setTimeout(resolve, 20));
                      window.XHR.get = originalGet;
                      const failureRestored = document.querySelector('input[name="radios"]:checked')?.value === 'rule';
                      return {staleRejected, optimistic, confirmed, staleAfterResponseRejected,
                              matchingPollAccepted, unknownRunModeCleared, failureRestored,
                              runtimeState: document.querySelector('.openkill-status-page')?.dataset.runtimeState};
                    }
                    """
                )
                if not all(probe.get(key) for key in ("staleRejected", "optimistic", "confirmed", "staleAfterResponseRejected", "matchingPollAccepted", "unknownRunModeCleared", "failureRestored")):
                    raise AssertionError(f"PRODUCTION_INTERACTION_PROBE_FAILED:{json.dumps(probe, ensure_ascii=False)}")

                visibility = page.evaluate(
                    """
                    () => {
                      const manager = window.openkillPreview.configManager;
                      if (!manager) throw new Error('PRODUCTION_CONFIG_MANAGER_MISSING');
                      const parent = document.createElement('section');
                      const child = document.createElement('button');
                      child.type = 'button';
                      parent.appendChild(child);
                      document.body.appendChild(parent);
                      child.focus();
                      manager.setVisibility(parent, false, 'flex');
                      const hiddenState = {hidden: parent.hidden, aria: parent.getAttribute('aria-hidden'),
                                           display: parent.style.display, focusEscaped: document.activeElement !== child};
                      manager.setVisibility(parent, true, 'flex');
                      const shownState = {hidden: parent.hidden, aria: parent.getAttribute('aria-hidden'),
                                          display: parent.style.display};
                      parent.remove();

                      const configPath = '/etc/openkill/config/long-local-preview-name.yaml';
                      manager.configList = [{path: configPath, name: 'long-local-preview-name.yaml',
                                             mtime: 1700000000, size: 8192, age: false}];
                      manager.rawCurrentConfig = configPath;
                      manager.currentConfig = configPath;
                      manager.updateSubscriptionDisplay(configPath, manager.configList[0]);
                      const details = document.getElementById('subscription-info-details');
                      const refresh = document.getElementById('refresh-subscription');
                      refresh.focus();
                      manager.hideSubscriptionDisplay();
                      const configHiddenState = {
                        containerHidden: document.getElementById('subscription-info-display').hidden,
                        detailsHidden: details.hidden,
                        detailsAria: details.getAttribute('aria-hidden'),
                        focusEscaped: document.activeElement !== refresh
                      };
                      manager.updateSubscriptionDisplay(configPath, manager.configList[0]);
                      const configShownState = {
                        containerHidden: document.getElementById('subscription-info-display').hidden,
                        detailsHidden: details.hidden,
                        detailsAria: details.getAttribute('aria-hidden'),
                        display: details.style.display
                      };
                      return {hiddenState, shownState, configHiddenState, configShownState};
                    }
                    """
                )
                if visibility["hiddenState"] != {"hidden": True, "aria": "true", "display": "none", "focusEscaped": True}:
                    raise AssertionError(f"PRODUCTION_VISIBILITY_HIDE_FAILED:{json.dumps(visibility, ensure_ascii=False)}")
                if visibility["shownState"] != {"hidden": False, "aria": "false", "display": "flex"}:
                    raise AssertionError(f"PRODUCTION_VISIBILITY_SHOW_FAILED:{json.dumps(visibility, ensure_ascii=False)}")
                if visibility["configHiddenState"] != {
                    "containerHidden": True,
                    "detailsHidden": True,
                    "detailsAria": "true",
                    "focusEscaped": True,
                }:
                    raise AssertionError(f"PRODUCTION_CONFIG_VISIBILITY_HIDE_FAILED:{json.dumps(visibility, ensure_ascii=False)}")
                if visibility["configShownState"] != {
                    "containerHidden": False,
                    "detailsHidden": False,
                    "detailsAria": "false",
                    "display": "flex",
                }:
                    raise AssertionError(f"PRODUCTION_CONFIG_VISIBILITY_SHOW_FAILED:{json.dumps(visibility, ensure_ascii=False)}")

                conditional = page.evaluate(
                    """
                    () => {
                      const host = document.createElement('section');
                      host.innerHTML = `
                        <div class="mode-tabs" role="tablist">
                          <button type="button" id="upload-mode-file" role="tab">File</button>
                          <button type="button" id="upload-mode-subscribe" role="tab">Subscribe</button>
                        </div>
                        <div id="mode-file-content"><div id="upload-zone" class="upload-zone"><span class="upload-primary"></span><span class="upload-secondary"></span></div></div>
                        <div id="mode-subscribe-content"></div>
                        <div id="config-upload-status-text"></div>
                        <input id="config-filename-input" value="">
                        <input id="subscribe-url-input" value="">
                        <input id="advanced-options-enable" type="checkbox">
                        <input id="advanced-options-enable-file" type="checkbox">
                        <input id="sub-convert-enable" type="checkbox">
                        <div id="advanced-options-container"><div id="age-encryption-group"><span>age</span></div></div>
                        <div id="advanced-options-container-file"></div>
                        <input id="age-public-input" value=""><input id="age-secret-input" value="">
                        <div id="hidden-conditional"><button type="button">child</button></div>
                        <button id="config-upload-submit" type="button"></button>
                      `;
                      document.body.appendChild(host);
                      const uploader = window.ConfigUploader;
                      uploader.isEditMode = false;
                      uploader.isProcessing = false;
                      uploader.selectedFile = null;
                      uploader.editFilename = null;
                      uploader.switchMode('file');
                      const fileState = {
                        tabSelected: document.getElementById('upload-mode-file').getAttribute('aria-selected'),
                        tabIndex: document.getElementById('upload-mode-file').tabIndex,
                        panelHidden: document.getElementById('mode-file-content').hidden,
                        panelAria: document.getElementById('mode-file-content').getAttribute('aria-hidden'),
                        otherHidden: document.getElementById('mode-subscribe-content').hidden
                      };
                      uploader.switchMode('subscribe');
                      const subscribeState = {
                        tabSelected: document.getElementById('upload-mode-subscribe').getAttribute('aria-selected'),
                        tabIndex: document.getElementById('upload-mode-subscribe').tabIndex,
                        panelHidden: document.getElementById('mode-subscribe-content').hidden,
                        panelAria: document.getElementById('mode-subscribe-content').getAttribute('aria-hidden'),
                        otherHidden: document.getElementById('mode-file-content').hidden
                      };
                      uploader.isEditMode = true;
                      uploader.switchMode('file');
                      const editState = {
                        hiddenFileTab: document.getElementById('upload-mode-file').hidden,
                        selectedSubscribe: document.getElementById('upload-mode-subscribe').getAttribute('aria-selected'),
                        selectedHidden: document.getElementById('upload-mode-file').getAttribute('aria-selected')
                      };
                      const parent = document.getElementById('hidden-conditional');
                      const child = parent.querySelector('button');
                      child.focus();
                      uploader.setVisibility(parent, false);
                      const focusEscaped = document.activeElement !== child;
                      const hiddenState = {hidden: parent.hidden, aria: parent.getAttribute('aria-hidden'), focusEscaped};
                      const ageNode = document.getElementById('age-encryption-group');
                      const ageSubscribe = document.getElementById('advanced-options-container');
                      const ageFile = document.getElementById('advanced-options-container-file');
                      const fileAdvanced = document.getElementById('advanced-options-enable-file');
                      uploader.currentMode = 'file';
                      fileAdvanced.checked = true;
                      uploader.syncAgeEncryptionPlacement();
                      const ageFilePlacement = ageNode.parentNode === ageFile;
                      uploader.switchMode('subscribe');
                      const ageSubscribePlacement = ageNode.parentNode === ageSubscribe;
                      fileAdvanced.checked = true;
                      uploader.resetAdvancedOptions();
                      const ageResetPlacement = {
                        parentIsSubscribe: ageNode.parentNode === ageSubscribe,
                        fileAdvancedChecked: fileAdvanced.checked,
                        ageVisible: !ageNode.hidden
                      };
                      host.remove();
                      return {fileState, subscribeState, editState, hiddenState,
                              ageFilePlacement, ageSubscribePlacement, ageResetPlacement};
                    }
                    """
                )
                expected_file = {
                    "tabSelected": "true", "tabIndex": 0, "panelHidden": False,
                    "panelAria": "false", "otherHidden": True
                }
                expected_subscribe = {
                    "tabSelected": "true", "tabIndex": 0, "panelHidden": False,
                    "panelAria": "false", "otherHidden": True
                }
                expected_edit = {
                    "hiddenFileTab": True, "selectedSubscribe": "true", "selectedHidden": "false"
                }
                expected_hidden = {"hidden": True, "aria": "true", "focusEscaped": True}
                if conditional.get("fileState") != expected_file:
                    raise AssertionError(f"PRODUCTION_UPLOAD_FILE_TAB_FAILED:{json.dumps(conditional, ensure_ascii=False)}")
                if conditional.get("subscribeState") != expected_subscribe:
                    raise AssertionError(f"PRODUCTION_UPLOAD_SUBSCRIBE_TAB_FAILED:{json.dumps(conditional, ensure_ascii=False)}")
                if conditional.get("editState") != expected_edit:
                    raise AssertionError(f"PRODUCTION_UPLOAD_EDIT_TAB_FAILED:{json.dumps(conditional, ensure_ascii=False)}")
                if conditional.get("hiddenState") != expected_hidden:
                    raise AssertionError(f"PRODUCTION_UPLOAD_HIDDEN_CHILD_FAILED:{json.dumps(conditional, ensure_ascii=False)}")
                if not conditional.get("ageFilePlacement") or not conditional.get("ageSubscribePlacement") or conditional.get("ageResetPlacement") != {
                    "parentIsSubscribe": True, "fileAdvancedChecked": False, "ageVisible": True
                }:
                    raise AssertionError(f"PRODUCTION_UPLOAD_AGE_PLACEMENT_FAILED:{json.dumps(conditional, ensure_ascii=False)}")

                editor_race = page.evaluate(
                    """
                    async () => {
                      const editor = window.ConfigEditor;
                      if (!editor) throw new Error('PRODUCTION_CONFIG_EDITOR_MISSING');
                      const host = document.createElement('section');
                      host.innerHTML = `
                        <div id="config-editor-overlay" class="show">
                          <div id="config-editor-model">
                            <div id="config-editor-status-text"></div>
                            <textarea id="config-editor-textarea"></textarea>
                            <div id="config-mergeview-container"></div>
                            <div id="config-mode-tabs"></div>
                          </div>
                        </div>
                      `;
                      document.body.appendChild(host);
                      editor.overlay = document.getElementById('config-editor-overlay');
                      editor.model = document.getElementById('config-editor-model');
                      editor.editorInstance = null;
                      editor._currentEditorMode = null;
                      editor.originalContent = '';
                      editor.runtimeContent = '';
                      editor.isOverwrite = false;
                      editor.currentViewMode = 'original';
                      editor.loadSequence = 0;
                      window.CM6 = {
                        themeExtension: () => ({}), baseExtensions: () => ({}), yaml: () => ({}),
                        yamlLinter: () => ({}), lintGutter: () => ({}),
                        autocompletion: () => ({}), indentUnit: {of: () => ({})},
                        indentMarkerExtension: () => ({}), placeholderExtension: () => ({}),
                        keymap: {of: () => ({})}, EditorState: {create: opts => ({doc: {length: (opts.doc || '').length}})},
                        EditorView: function (opts) { this.dom = document.createElement('div'); opts.parent.appendChild(this.dom); },
                        mirrorThemeScrollbar: () => {}
                      };
                      window.CM6.EditorView.updateListener = {of: () => ({})};
                      window.CM6.EditorState.readOnly = {of: () => ({})};
                      const originalFetch = window.fetch;
                      const pending = {};
                      window.fetch = url => new Promise(resolve => { pending[url] = resolve; });
                      editor.currentConfigFile = '/etc/openkill/config/first.yaml';
                      editor.loadConfigContent();
                      const firstUrl = Object.keys(pending)[0];
                      editor.currentConfigFile = '/etc/openkill/config/second.yaml';
                      editor.loadConfigContent();
                      const secondUrl = Object.keys(pending).find(url => url !== firstUrl);
                      pending[firstUrl]({ok: true, json: async () => ({status: 'success', content: 'FIRST'})});
                      pending[secondUrl]({ok: true, json: async () => ({status: 'success', content: 'SECOND'})});
                      await new Promise(resolve => setTimeout(resolve, 0));
                      const result = {
                        content: editor.originalContent,
                        status: document.getElementById('config-editor-status-text').textContent,
                        staleDidNotWin: editor.originalContent === 'SECOND'
                      };
                      window.fetch = originalFetch;
                      host.remove();
                      return result;
                    }
                    """
                )
                if editor_race != {
                    "content": "SECOND",
                    "status": "Ready",
                    "staleDidNotWin": True,
                }:
                    raise AssertionError(f"PRODUCTION_EDITOR_RACE_FAILED:{json.dumps(editor_race, ensure_ascii=False)}")

                overwrite_controls = page.evaluate(
                    """
                    () => {
                      const editor = window.ConfigEditor;
                      if (!editor) throw new Error('PRODUCTION_CONFIG_EDITOR_MISSING');
                      const host = document.createElement('section');
                      const bar = document.createElement('div');
                      const list = document.createElement('div');
                      list.id = 'overwrite-card-list';
                      bar.id = 'overwrite-card-bar';
                      bar.appendChild(list);
                      host.appendChild(bar);
                      document.body.appendChild(host);

                      editor.overwriteCardBar = bar;
                      editor.isOverwrite = true;
                      editor.currentConfigFile = '/etc/openkill/overwrite/alpha.sh';
                      editor.overwriteFiles = [
                        {name: 'openkill_custom_overwrite.sh', path: '/etc/openkill/custom/openkill_custom_overwrite.sh'},
                        {name: 'alpha.sh', path: '/etc/openkill/overwrite/alpha.sh'},
                        {name: 'beta.sh', path: '/etc/openkill/overwrite/beta.sh'}
                      ];
                      editor.overwriteSubInfo = {
                        'alpha.sh': {enable: 1, type: 'file'},
                        'beta.sh': {enable: 0, type: 'file'}
                      };
                      editor.saveOverwriteSort = () => {};
                      editor.loadOverwriteFiles = () => {};
                      editor.showOverwriteSubmodel = () => {};

                      const nativeAdd = list.addEventListener.bind(list);
                      const delegatedCounts = {dragover: 0, dragleave: 0, drop: 0, touchmove: 0, touchend: 0};
                      list.addEventListener = (type, listener, options) => {
                        if (Object.prototype.hasOwnProperty.call(delegatedCounts, type)) delegatedCounts[type]++;
                        return nativeAdd(type, listener, options);
                      };
                      editor.renderOverwriteCards();
                      editor.renderOverwriteCards();
                      const renderState = {
                        delegatedCounts,
                        activeCards: list.querySelectorAll('.overwrite-item.active').length,
                        cardNames: Array.from(list.querySelectorAll('.overwrite-item .overwrite-title')).map(el => el.textContent)
                      };

                      editor.getOverwriteConfigFiles = () => [
                        {name: 'alpha.yaml', path: '/etc/openkill/config/alpha.yaml'},
                        {name: 'beta.yaml', path: '/etc/openkill/config/beta.yaml'}
                      ];
                      const dropdownHost = document.createElement('div');
                      dropdownHost.innerHTML = editor.renderOverwriteConfigDropdown('', 'browser-overwrite-dropdown');
                      document.body.appendChild(dropdownHost);
                      const container = dropdownHost.firstElementChild;
                      editor.bindOverwriteConfigDropdown(container);
                      const button = container.querySelector('.overwrite-config-dropdown-btn');
                      const panel = container.querySelector('.overwrite-config-dropdown-panel');
                      button.click();
                      const opened = {hidden: panel.hidden, aria: button.getAttribute('aria-expanded')};
                      const beta = container.querySelector('input[value="/etc/openkill/config/beta.yaml"]');
                      beta.checked = true;
                      beta.dispatchEvent(new Event('change', {bubbles: true}));
                      const selectedBeta = {
                        allChecked: container.querySelector('input[value="all"]').checked,
                        betaChecked: beta.checked,
                        betaSelected: beta.closest('.overwrite-config-option').classList.contains('selected'),
                        betaAria: beta.closest('.overwrite-config-option').getAttribute('aria-checked')
                      };
                      const all = container.querySelector('input[value="all"]');
                      all.checked = true;
                      all.dispatchEvent(new Event('change', {bubbles: true}));
                      const selectedAll = {
                        allChecked: all.checked,
                        betaChecked: beta.checked,
                        betaDisabled: beta.disabled,
                        betaAriaDisabled: beta.closest('.overwrite-config-option').getAttribute('aria-disabled')
                      };
                      button.focus();
                      button.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
                      const keyboardOpen = panel.hidden;
                      button.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
                      const escaped = {hidden: panel.hidden, focusRestored: document.activeElement === button};
                      dropdownHost.remove();
                      host.remove();
                      return {renderState, opened, selectedBeta, selectedAll, keyboardOpen, escaped};
                    }
                    """
                )
                if overwrite_controls["renderState"]["delegatedCounts"] != {
                    "dragover": 1, "dragleave": 1, "drop": 1, "touchmove": 1, "touchend": 1
                }:
                    raise AssertionError(f"PRODUCTION_OVERWRITE_HANDLER_DUPLICATION:{json.dumps(overwrite_controls, ensure_ascii=False)}")
                if overwrite_controls["renderState"]["activeCards"] != 1:
                    raise AssertionError(f"PRODUCTION_OVERWRITE_ACTIVE_CARD_FAILED:{json.dumps(overwrite_controls, ensure_ascii=False)}")
                if overwrite_controls["opened"] != {"hidden": False, "aria": "true"}:
                    raise AssertionError(f"PRODUCTION_OVERWRITE_DROPDOWN_OPEN_FAILED:{json.dumps(overwrite_controls, ensure_ascii=False)}")
                if overwrite_controls["selectedBeta"] != {
                    "allChecked": False, "betaChecked": True, "betaSelected": True, "betaAria": "true"
                }:
                    raise AssertionError(f"PRODUCTION_OVERWRITE_OPTION_SELECT_FAILED:{json.dumps(overwrite_controls, ensure_ascii=False)}")
                if overwrite_controls["selectedAll"] != {
                    "allChecked": True, "betaChecked": False, "betaDisabled": True, "betaAriaDisabled": "true"
                }:
                    raise AssertionError(f"PRODUCTION_OVERWRITE_ALL_EXCLUSIVE_FAILED:{json.dumps(overwrite_controls, ensure_ascii=False)}")
                if not overwrite_controls["keyboardOpen"] or overwrite_controls["escaped"] != {"hidden": True, "focusRestored": True}:
                    raise AssertionError(f"PRODUCTION_OVERWRITE_KEYBOARD_FAILED:{json.dumps(overwrite_controls, ensure_ascii=False)}")

                page.locator('label[for="global"]').click()
                page.wait_for_timeout(20)
                if not page.locator("#global").is_checked():
                    raise AssertionError("PRODUCTION_LABEL_CLICK_FAILED:global")
                page.locator('label[for="rule"]').click()
                page.wait_for_timeout(20)
                if not page.locator("#rule").is_checked():
                    raise AssertionError("PRODUCTION_LABEL_CLICK_FAILED:rule")

                dimensions: list[dict[str, object]] = []
                for width in (1920, 1366, 768, 390):
                    page.set_viewport_size({"width": width, "height": 900})
                    page.wait_for_timeout(20)
                    metrics = page.evaluate(
                        """
                        () => ({
                          width: window.innerWidth,
                          scrollWidth: document.documentElement.scrollWidth,
                          bodyScrollWidth: document.body.scrollWidth,
                          selectedRule: document.querySelector('input[name="radios"]:checked')?.value || '',
                          selectedRun: document.querySelector('input[name="radios-ru"]:checked')?.value || '',
                          focusVisibleRule: getComputedStyle(document.querySelector('input[name="radios"] + .cbi-button-option')).outlineStyle
                        })
                        """
                    )
                    metrics["noHorizontalOverflow"] = metrics["scrollWidth"] <= width and metrics["bodyScrollWidth"] <= width
                    dimensions.append(metrics)
                    page.screenshot(path=str(EVIDENCE_DIR / f"dynamic-{width}.png"), full_page=True)
                if not all(bool(item["noHorizontalOverflow"]) for item in dimensions):
                    raise AssertionError(f"UI_HORIZONTAL_OVERFLOW:{json.dumps(dimensions)}")
                if console_errors or page_errors or blocked_requests:
                    raise AssertionError(
                        "UI_BROWSER_ERRORS:"
                        f"console={console_errors},page={page_errors},blocked={blocked_requests},requests={requests}"
                    )

                evidence = {
                    "source": "production status.htm + production CSS + production SettingsManager",
                    "mock_backend": "local in-page XHR only",
                    "browser_executable": str(executable),
                    "dimensions": dimensions,
                    "probe": probe,
                    "visibility": visibility,
                    "conditional": conditional,
                    "editor_race": editor_race,
                    "requests": requests,
                    "console_errors": console_errors,
                    "page_errors": page_errors,
                    "blocked_requests": blocked_requests,
                }
                (EVIDENCE_DIR / "dynamic-browser-evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
                print("UI_BROWSER=PASS")
                print("UI_PRODUCTION_JS=PASS")
                print("UI_DIMENSIONS=4/4")
                print("UI_LOCAL_REQUESTS=PASS")
                return 0
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    # The Playwright context closes the browser when the
                    # surrounding context exits; avoid masking the test
                    # result while cleaning up after an assertion failure.
                    pass
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
