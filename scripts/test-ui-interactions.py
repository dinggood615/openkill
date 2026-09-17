#!/usr/bin/env python3
"""Exercise the production status-page control coordinator in isolation.

The test extracts ``SettingsManager`` from the real LuCI view and executes the
unchanged JavaScript in a tiny DOM/XHR harness.  The harness has no network and
does not reimplement the coordinator, so stale polling and out-of-order
responses are tested against the production event logic itself.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "luci-app-openkill/luasrc/view/openkill/status.htm"


def production_settings_source() -> str:
    source = STATUS.read_text(encoding="utf-8")
    start = source.index("    var SettingsManager = {")
    end = source.index("\n    var pluginToggleUserAction", start)
    return source[start:end]


NODE_HARNESS = r"""
const vm = require('vm');
const productionSource = __PRODUCTION_SOURCE__;

function fail(message) { throw new Error(message); }
function expect(condition, message) { if (!condition) fail(message); }
function tick(ms) { return new Promise((resolve) => setTimeout(resolve, ms || 0)); }

function control(id, name, value) {
  return {
    id: id, name: name, value: value, checked: false, disabled: false,
    dispatchEvent: function () { this.dispatched = (this.dispatched || 0) + 1; },
    blur: function () { this.blurred = true; }
  };
}

const elements = {};
const byName = {};
function add(id, name, value) {
  const item = control(id, name, value);
  elements[id] = item;
  if (!byName[name]) byName[name] = [];
  byName[name].push(item);
  return item;
}

const rule = add('rule', 'radios', 'rule');
const globalMode = add('global', 'radios', 'global');
const direct = add('direct', 'radios', 'direct');
const normal = add('normal', 'radios-ru', '');
const tun = add('tun', 'radios-ru', '-tun');
const mix = add('mix', 'radios-ru', '-mix');
const oversea0 = add('oc_setting_oversea_0', 'oc-setting-oversea', '0');
const oversea1 = add('oc_setting_oversea_1', 'oc-setting-oversea', '1');
const oversea2 = add('oc_setting_oversea_2', 'oc-setting-oversea', '2');
const snifferOn = add('meta_sniffer_on', 'meta-sniffer-radios', '1');
const snifferOff = add('meta_sniffer_off', 'meta-sniffer-radios', '0');
const respectOn = add('respect_rules_on', 'respect-rules-radios', '1');
const respectOff = add('respect_rules_off', 'respect-rules-radios', '0');
const unlockOn = add('stream_unlock_on', 'stream-unlock-radios', '1');
const unlockOff = add('stream_unlock_off', 'stream-unlock-radios', '0');

const DOMCache = {
  radio: byName.radios, radio_ru: byName['radios-ru'],
  meta_sniffer_on: snifferOn, meta_sniffer_off: snifferOff,
  respect_rules_on: respectOn, respect_rules_off: respectOff,
  oc_setting_oversea_0: oversea0, oc_setting_oversea_1: oversea1,
  oc_setting_oversea_2: oversea2,
  stream_unlock_on: unlockOn, stream_unlock_off: unlockOff
};

const document = {
  activeElement: null,
  getElementById: function (id) { return elements[id] || null; },
  getElementsByName: function (name) { return byName[name] || []; },
  querySelectorAll: function () { return []; }
};

const requests = [];
const alerts = [];
const XHR = {
  get: function (endpoint, params, callback) {
    requests.push({ endpoint: endpoint, params: params, callback: callback });
  }
};
function alert(message) { alerts.push(message); }

const context = {
  DOMCache: DOMCache, document: document, XHR: XHR, alert: alert,
  console: console, setTimeout: setTimeout, clearTimeout: clearTimeout,
  Date: Date, Object: Object, Set: Set, String: String, Array: Array,
  isFinite: isFinite, openkillRuntimeState: 'running'
};
vm.runInNewContext(productionSource + '\nthis.SettingsManager = SettingsManager;', context, {
  filename: 'status.htm#SettingsManager'
});
const manager = context.SettingsManager;
manager.responseSettleDelay = 0;
manager.confirmationTimeout = 30;

function reset(setting, value) {
  context.openkillRuntimeState = 'running';
  for (const item of Object.values(elements)) {
    item.checked = false;
    item.disabled = false;
    item.dispatched = 0;
  }
  manager.pendingOperations = new Set();
  manager.pendingBySetting = Object.create(null);
  manager.confirmedValues = Object.create(null);
  manager.pausedPolls = new Set();
  for (const key of Object.keys(manager.pauseTimers || {})) clearTimeout(manager.pauseTimers[key]);
  manager.pauseTimers = Object.create(null);
  alerts.length = 0;
  requests.length = 0;
  manager.setControls(setting, value, false);
}

async function settle(index, status) {
  requests[index].callback({ status: status }, {});
  await tick(0);
}

async function stalePollDoesNotRevert() {
  reset('rule_mode', 'rule');
  manager.switchSetting('rule_mode', 'global', '/mock');
  expect(globalMode.checked && !rule.checked, 'optimistic rule selection was not applied');
  expect(globalMode.disabled && rule.disabled, 'rule group was not locked during request');
  expect(!manager.shouldApplyPoll('rule_mode', 'rule'), 'stale rule poll overwrote optimistic selection');
  expect(globalMode.checked, 'stale rule poll changed selected control');
  await settle(0, 200);
  expect(globalMode.checked && !globalMode.disabled, 'successful response did not retain selection');
  expect(!manager.shouldApplyPoll('rule_mode', 'rule'), 'stale post-response poll was accepted');
  expect(manager.shouldApplyPoll('rule_mode', 'global'), 'matching rule poll did not confirm request');
  expect(manager.pendingOperations.size === 0, 'confirmed rule operation remained pending');
}

async function latestRequestWins() {
  reset('rule_mode', 'rule');
  manager.switchSetting('rule_mode', 'global', '/mock');
  manager.switchSetting('rule_mode', 'direct', '/mock');
  expect(direct.checked && !globalMode.checked, 'latest quick selection was not applied');
  await settle(0, 200);
  expect(direct.checked, 'old response changed the latest selection');
  await settle(1, 200);
  expect(!manager.shouldApplyPoll('rule_mode', 'global'), 'old poll value won after quick switch');
  expect(manager.shouldApplyPoll('rule_mode', 'direct'), 'latest poll value did not confirm');
}

async function failedRequestRestoresConfirmed() {
  reset('rule_mode', 'rule');
  manager.switchSetting('rule_mode', 'global', '/mock');
  await settle(0, 500);
  expect(rule.checked && !globalMode.checked, 'failed request did not restore confirmed value');
  expect(!rule.disabled && !globalMode.disabled, 'failed request left controls disabled');
  expect(alerts.length === 1, 'failed request did not report exactly one error');
}

async function runModeUsesSemanticValue() {
  reset('run_mode', '');
  manager.switchSetting('run_mode', '-tun', '/mock');
  expect(tun.checked, 'run-mode optimistic selection was not applied');
  expect(!manager.shouldApplyPoll('run_mode', 'fake-ip'), 'base mode poll reverted tun choice');
  await settle(0, 200);
  expect(manager.shouldApplyPoll('run_mode', 'fake-ip-tun'), 'complete backend mode did not confirm tun choice');
  expect(manager.normalizeValue('run_mode', 'future-tun-mode') === 'future-tun-mode', 'unknown run mode was treated as a known suffix');
  manager.setControls('run_mode', 'future-mode', false);
  expect(!normal.checked && !tun.checked && !mix.checked, 'unknown run mode left a stale selected child');
}

async function otherSettingGroupsUseSameStateMachine() {
  reset('oversea', '0');
  manager.switchSetting('oversea', '2', '/mock');
  expect(oversea2.checked && !oversea0.checked && oversea2.disabled, 'multi-option group was not synchronized');
  expect(!manager.shouldApplyPoll('oversea', '0'), 'stale multi-option poll was accepted');
  await settle(0, 200);
  expect(manager.shouldApplyPoll('oversea', '2'), 'matching multi-option poll did not confirm');
  expect(!oversea2.disabled, 'confirmed multi-option group remained disabled');
}

async function confirmationTimeoutReturnsToBackendTruth() {
  reset('rule_mode', 'rule');
  manager.switchSetting('rule_mode', 'global', '/mock');
  await settle(0, 200);
  await tick(40);
  expect(manager.shouldApplyPoll('rule_mode', 'rule'), 'expired confirmation window did not accept backend truth');
  expect(rule.checked && !globalMode.checked, 'backend truth was not restored after timeout');
}

async function runtimeTransitionDoesNotReenableControls() {
  reset('rule_mode', 'rule');
  manager.switchSetting('rule_mode', 'global', '/mock');
  context.openkillRuntimeState = 'stopped';
  await settle(0, 200);
  expect(globalMode.checked, 'late response lost the requested value');
  expect(globalMode.disabled && rule.disabled, 'stopped runtime re-enabled a setting group');
  context.openkillRuntimeState = 'running';
  expect(manager.shouldApplyPoll('rule_mode', 'global'), 'running state did not accept confirmation');
  expect(!globalMode.disabled && !rule.disabled, 'confirmed running setting remained disabled');
}

(async function () {
  await stalePollDoesNotRevert();
  await latestRequestWins();
  await failedRequestRestoresConfirmed();
  await runModeUsesSemanticValue();
  await otherSettingGroupsUseSameStateMachine();
  await confirmationTimeoutReturnsToBackendTruth();
  await runtimeTransitionDoesNotReenableControls();
  console.log('UI_INTERACTIONS=PASS');
  console.log(JSON.stringify({ cases: 7, requests: requests.length }));
})().catch(function (error) {
  console.error('UI_INTERACTIONS=FAIL ' + error.message);
  process.exitCode = 1;
});
"""


class ProductionStatusInteractionTests(unittest.TestCase):
    def test_production_settings_manager_handles_poll_and_request_races(self) -> None:
        node = shutil.which("node")
        if not node:
            self.skipTest("NODE_UNAVAILABLE")
        script = NODE_HARNESS.replace(
            "__PRODUCTION_SOURCE__", json.dumps(production_settings_source())
        )
        with tempfile.TemporaryDirectory(prefix="openkill-ui-interactions-") as directory:
            path = Path(directory) / "test.js"
            path.write_text(textwrap.dedent(script), encoding="utf-8")
            result = subprocess.run(
                [node, str(path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("UI_INTERACTIONS=PASS", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
