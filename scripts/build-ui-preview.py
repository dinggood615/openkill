#!/usr/bin/env python3
"""Build a local-only preview from the real OpenKill status templates.

The preview intentionally contains no LuCI backend and no network requests.  It
extracts the production view markup, keeps the production CSS/asset URLs, and
adds a small in-page fixture driver so browser checks can exercise presentation
states without contacting a router.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
VIEW_ROOT = ROOT / "luci-app-openkill/luasrc/view/openkill"


TRANSLATIONS = {
    "Running Status": "运行状态",
    "OpenKill runtime status": "OpenKill 运行状态",
    "Restart": "重启",
    "Overwrite Module": "覆写模块",
    "Auto Theme": "自动主题",
    "Running Mode": "运行模式",
    "Proxy Mode": "代理模式",
    "Area Bypass": "区域绕过",
    "Sniffer": "域名嗅探",
    "DNS Proxy": "DNS 代理",
    "Stream Unlock": "流媒体解锁",
    "Config File": "配置文件",
    "Previous": "上一个",
    "Next": "下一个",
    "Modified": "已修改",
    "Specify URL": "指定 URL",
    "Add Config File": "添加配置文件",
    "SwiTch": "切换",
    "Update": "更新",
    "Edit": "编辑",
    "Edit Subscription": "编辑订阅",
    "Add": "添加",
    "Control Panel": "控制面板",
    "Copy Address": "复制地址",
    "Copy Secret": "复制密钥",
    "Mix Proxy": "混合代理",
    "Get PAC Config": "获取 PAC 配置",
    "Copy Auth Info": "复制认证信息",
    "Quick Action": "快捷操作",
    "IP Address": "IP 地址",
    "Access Check": "访问检查",
    "Collecting data...": "加载中…",
    "Not Running": "未运行",
    "Disabled": "已禁用",
    "Unknown": "未知",
    "Error": "错误",
    "Start Failed": "启动失败",
    "Not Available": "暂无数据",
    "Running": "运行中",
    "Stable": "稳定",
    "Watchdog": "守护进程",
    "IPv6 disabled": "IPv6 未启用",
    "IPv6 + DNS": "IPv6 + DNS",
    "IPv6": "IPv6",
    "IPv4": "IPv4",
    "Compat": "增强",
    "TUN": "TUN",
    "Mix": "混合",
    "Rule": "规则",
    "Global": "全局",
    "Direct": "直连",
    "Mainland": "大陆",
    "Oversea": "海外",
    "Off": "停用",
    "On": "启用",
    "Yacd": "Yacd",
    "Dashboard": "Dashboard",
    "Metacubexd": "Metacubexd",
    "Zashboard": "Zashboard",
    "Close Connect": "关闭连接",
    "Reload Firewall": "重置防火墙",
    "Flush DNS": "清理 DNS 缓存",
    "Flush DNS Cache": "清理 DNS 缓存",
    "Check Update": "检查更新",
    "Up": "上传",
    "Down": "下载",
    "Up Total": "上传总量",
    "Down Total": "下载总量",
    "Connect": "活动连接",
    "Ram": "内存占用",
    "CPU": "CPU 占用",
    "Load Avg": "系统负载",
    "Info": "信息",
    "Warning": "警告",
    "Debug": "调试",
    "Tip": "提示",
    "Fatal": "致命",
    "Baidu Search": "百度搜索",
    "NetEase Music": "网易云音乐",
    "Testing...": "检查中…",
    "Querying...": "查询中…",
    "Access Normal": "访问正常",
    "Access Timed Out": "访问超时",
    "Access Denied": "访问被拒绝",
    "Show IP": "显示 IP",
    "Browser Mode": "浏览器模式",
    "Timeout": "超时",
    "Unavailable": "不可用",
    "Router Mode": "路由模式",
    "Refresh": "刷新",
    "Hide IP": "隐藏 IP",
    "No Config Selected": "未选择配置",
}


def _translate(match: re.Match[str]) -> str:
    value = match.group(1).strip()
    return TRANSLATIONS.get(value, value)


def _clean_markup(source: str) -> str:
    source = re.sub(r"<%:([^%]+)%>", _translate, source)
    source = source.replace("<%=plugin_version%>", "local-preview")
    # Keep the preview offline. The production templates contain links to
    # optional documentation and image paths rooted at LuCI's web directory;
    # rewrite those presentation-only references to local equivalents.
    source = re.sub(r"https?://[^\"' )]+", "#local-preview", source)
    source = source.replace("javascript:void(0)", "#")
    source = source.replace('src="/luci-static/', 'src="/luci-app-openkill/root/www/luci-static/')
    # The extracted fragments contain only display markup.  Any remaining Lua
    # template expression is removed rather than evaluated in the browser.
    source = re.sub(r"<%.*?%>", "", source, flags=re.DOTALL)
    return source


def _extract_status() -> str:
    source = (VIEW_ROOT / "status.htm").read_text(encoding="utf-8")
    start = source.index('<div class="oc openkill-status-page"')
    end = source.index('\n<script type="text/javascript">\n// The status view', start)
    status = source[start:end].rstrip()
    header = (
        '<section class="openkill-page-header" aria-labelledby="openkill-page-title">'
        '<div class="openkill-page-header-main">'
        '<h1 id="openkill-page-title" class="openkill-page-title">运行状态</h1>'
        '<p class="openkill-page-description">查看 OpenKill 核心、网络和系统资源运行状态。</p>'
        "</div><div class=\"openkill-page-header-actions\" data-openkill-header-actions=\"1\"></div>"
        "</section>"
    )
    return _clean_markup(status.replace('<%+openkill/page_header%>', header))


def _extract_settings_manager() -> str:
    """Extract the production status control coordinator for the preview.

    The full LuCI status script needs a router-backed XHR environment, so the
    preview cannot execute it wholesale.  The settings coordinator is
    self-contained and owns the radio/segmented-control race fixes; injecting
    this exact source into a local mock lets browser checks exercise production
    event handling without copying that logic into a preview-only script.
    """
    source = (VIEW_ROOT / "status.htm").read_text(encoding="utf-8")
    start = source.index("    var SettingsManager = {")
    end = source.index("\n    var pluginToggleUserAction", start)
    return _clean_markup(source[start:end].strip())


def _extract_config_file_manager() -> str:
    """Extract the production config visibility coordinator for browser QA."""
    source = (VIEW_ROOT / "status.htm").read_text(encoding="utf-8")
    start = source.index("    var ConfigFileManager = {")
    end = source.index("\n    var SubscriptionManager = {", start)
    return _clean_markup(source[start:end].strip())


def _extract_status_visibility_helper() -> str:
    """Extract the production hidden-state helper used by optional controls."""
    source = (VIEW_ROOT / "status.htm").read_text(encoding="utf-8")
    start = source.index("    function setStatusVisibility(element, visible, displayValue, hiddenClass)")
    end = source.index("\n    function clearRuntimeUnavailableMarkers", start)
    return _clean_markup(source[start:end].strip()) + "\nwindow.openkillSetStatusVisibility = setStatusVisibility;"


def _extract_config_uploader() -> str:
    """Extract the production mode/conditional-control coordinator.

    The full uploader needs LuCI endpoints, so the browser harness supplies a
    local DOM fixture while executing this exact production object.  Only its
    event/state methods are exercised; no upload request is sent.
    """
    source = (VIEW_ROOT / "config_upload.htm").read_text(encoding="utf-8")
    start = source.index("var ConfigUploader = {")
    end = source.index("\n};\n\ndocument.addEventListener('DOMContentLoaded'", start) + len("\n};")
    return _clean_markup(source[start:end].strip()) + "\nwindow.ConfigUploader = ConfigUploader;"


def _extract_config_editor() -> str:
    """Extract the production editor state coordinator for race testing."""
    source = (VIEW_ROOT / "config_edit.htm").read_text(encoding="utf-8")
    start = source.index("var ConfigEditor = {")
    end = source.index("\n};\n\ndocument.addEventListener('DOMContentLoaded'", start) + len("\n};")
    return _clean_markup(source[start:end].strip()) + "\nwindow.ConfigEditor = ConfigEditor;"


def _extract_myip() -> str:
    source = (VIEW_ROOT / "myip.htm").read_text(encoding="utf-8")
    start = source.index('<fieldset class="cbi-section">')
    end = source.index("</fieldset>", start) + len("</fieldset>")
    return _clean_markup(source[start:end])


PREVIEW_STYLE = r"""
        :root { color-scheme: dark; }
        html, body { min-height: 100%; }
        body {
            margin: 0;
            padding: 18px;
            box-sizing: border-box;
            background: #17191d;
            color: #e8eaf0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", "Microsoft YaHei", sans-serif;
        }
        .openkill-preview-banner {
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 8px;
            margin: 0 auto 12px;
            max-width: 1920px;
            padding: 8px 12px;
            border: 1px solid #3d4655;
            border-radius: 7px;
            background: #202b3a;
            color: #c8d0df;
            font-size: 12px;
        }
        .openkill-preview-banner strong { color: #9b8cff; }
        .openkill-preview-controls { display: inline-flex; flex-wrap: wrap; gap: 4px; }
        .openkill-preview-controls button {
            min-height: 28px;
            padding: 3px 8px;
            border: 1px solid #414650;
            border-radius: 5px;
            background: #25282e;
            color: #e8eaf0;
            cursor: pointer;
        }
        .openkill-preview-controls button:hover,
        .openkill-preview-controls button:focus-visible { border-color: #9b8cff; outline: 2px solid rgba(155,140,255,.28); }
        .cbi-section { margin: 0; padding: 0; border: 0; background: transparent; }
        .cbi-section > table { width: 100%; border-collapse: collapse; }
        .cbi-section > table > tbody > tr > td { padding: 0; border: 0; }
        .openkill-preview-page { max-width: 1920px; margin: 0 auto; }
        .openkill-preview-page .openkill-status-page { padding-bottom: 0; }
        .openkill-preview-page .oc:not(.openkill-status-page) { width: 100%; max-width: none; }
        .openkill-preview-page .myip-main-card,
        .openkill-preview-page .myip-content-grid { width: 100%; max-width: none; }
        .openkill-preview-page .myip-main-card { margin-top: 12px; }
        .openkill-preview-page [data-preview-overflow] { overflow-wrap: anywhere; word-break: break-word; }
        @media (max-width: 640px) {
            body { padding: 10px; }
            .openkill-preview-banner { align-items: flex-start; flex-direction: column; }
            .openkill-preview-controls { width: 100%; }
            .openkill-preview-controls button { flex: 1 1 30%; }
        }
"""


PREVIEW_SCRIPT = r"""
        (function () {
            var page = document.querySelector('.openkill-status-page');
            var states = {
                loading: '加载中…', running: 'Meta&nbsp;运行中', stopped: '未运行',
                disabled: '已禁用', startup_failed: '启动失败', unknown: '暂无数据', error: '状态读取失败'
            };
            var values = {
                '_daip': '192.0.2.1:9090', '_mix_proxy': '198.51.100.2:7893',
                'upload_': '0 B/s', 'download_': '35.9 KB/s', 'uploadtotal_': '131.1 MB',
                'downloadtotal_': '2.8 GB', 'connect_t': '8', 'mem_t': '149.7 MB',
                'cpu_t': '0 %', 'load_a': '1 %', 'current-config-name': '3e2-safe.yaml',
                'file-modify-time-value': '本地模拟 · 刚刚'
            };

            function setState(state) {
                if (!page) return;
                page.dataset.runtimeState = state;
                page.setAttribute('aria-busy', state === 'loading' ? 'true' : 'false');
                var live = state === 'running';
                var unavailable = state === 'loading' ? '加载中…' : '暂无数据';
                var indicator = document.getElementById('_clash');
                if (indicator) {
                    indicator.dataset.state = state;
                    indicator.innerHTML = '<b>' + states[state] + '</b>';
                    indicator.setAttribute('aria-label', states[state].replace(/&nbsp;|<[^>]+>/g, ' '));
                }
                var toggle = document.getElementById('plugin_toggle');
                if (toggle) {
                    toggle.checked = state === 'running';
                    toggle.disabled = state === 'loading' || state === 'unknown' || state === 'error';
                }
                var profile = {
                    'runtime-core-chip': state === 'running' ? 'Meta 稳定' : (state === 'loading' ? '加载中…' : '暂无数据'),
                    'runtime-compatibility-chip': state === 'running' ? '高性能双栈' : (state === 'loading' ? '加载中…' : '未验证'),
                    'runtime-ipv6-chip': state === 'running' ? 'IPv6 + DNS' : (state === 'loading' ? '加载中…' : '未验证'),
                    'runtime-watchdog-chip': state === 'running' ? '守护进程 60s' : (state === 'loading' ? '加载中…' : '未验证')
                };
                Object.keys(profile).forEach(function (id) {
                    var chip = document.getElementById(id);
                    var label = chip && chip.querySelector('span:last-child');
                    if (label) label.textContent = profile[id];
                    if (chip) {
                        chip.classList.toggle('runtime-chip-success', state === 'running' && id !== 'runtime-core-chip');
                        chip.classList.toggle('runtime-chip-muted', state !== 'running');
                    }
                });

                ['_daip', '_mix_proxy', 'upload_', 'download_', 'uploadtotal_', 'downloadtotal_',
                 'connect_t', 'mem_t', 'cpu_t', 'load_a'].forEach(function (id) {
                    var value = document.getElementById(id);
                    if (value) value.textContent = live ? (values[id] || '—') : unavailable;
                });
                var mode = document.getElementById('_mode');
                if (mode) mode.textContent = live ? 'TUN' : unavailable;
                ['_web', '_webo', '_webm', '_webz', '_close_all_connection_btn',
                 '_reload_firewall_btn', '_flush_dns_cache_btn', '_one_key_update_btn'].forEach(function (id) {
                    var action = document.getElementById(id);
                    if (!action) return;
                    action.disabled = !live;
                    action.classList.toggle('runtime-unavailable', !live);
                });
            }

            Object.keys(values).forEach(function (id) {
                var element = document.getElementById(id);
                if (element) element.textContent = values[id];
            });
            var dashboardLabels = {
                '_web': 'Yacd', '_webo': 'Dashboard', '_webm': 'Metacubexd', '_webz': 'Zashboard',
                '_close_all_connection_btn': '关闭连接', '_reload_firewall_btn': '重置防火墙',
                '_flush_dns_cache_btn': '清理 DNS 缓存', '_one_key_update_btn': '检查更新'
            };
            Object.keys(dashboardLabels).forEach(function (id) {
                var control = document.getElementById(id);
                if (control) control.textContent = dashboardLabels[id];
            });
            ['_web', '_webo', '_webz'].forEach(function (id) {
                var optionalDashboard = document.getElementById(id);
                if (optionalDashboard) {
                    window.openkillSetStatusVisibility(optionalDashboard, false, undefined, 'hidden');
                }
            });
            var activeDashboard = document.getElementById('_webm');
            if (activeDashboard) {
                window.openkillSetStatusVisibility(activeDashboard, true, undefined, 'hidden');
            }
            ['plugin-version-display', 'core-version-display'].forEach(function (id) {
                var item = document.getElementById(id);
                if (item) window.openkillSetStatusVisibility(item, true, undefined, 'oc-hidden');
            });
            var pluginVersion = document.getElementById('plugin-version-text');
            var coreVersion = document.getElementById('core-version-text');
            if (pluginVersion) pluginVersion.textContent = 'v2026-1138';
            if (coreVersion) coreVersion.textContent = 'v1.19.31';
            var mode = document.getElementById('_mode');
            if (mode) mode.innerHTML = '<b>TUN</b>';
            ['tun', 'rule', 'oc_setting_oversea_1', 'meta_sniffer_off', 'respect_rules_off', 'stream_unlock_off'].forEach(function (id) {
                var input = document.getElementById(id);
                if (input) input.checked = true;
            });
            var selector = document.getElementById('config_file_select');
            if (selector) selector.innerHTML = '<option value="3e2-safe.yaml" selected>3e2-safe.yaml</option>';
            ['ip-pcol', 'ip-ipip', 'ip-ipsb', 'ip-ipify'].forEach(function (id, index) {
                var item = document.getElementById(id);
                if (item) item.textContent = ['192.0.2.10', '192.0.2.11', '198.51.100.10', '198.51.100.11'][index];
            });
            ['ip-pcol-geo', 'ip-ipip-geo', 'ip-ipsb-geo', 'ip-ipify-geo'].forEach(function (id) {
                var item = document.getElementById(id);
                if (item) item.textContent = '本地模拟数据';
            });
            [['baidu','103'], ['163','51'], ['github','107'], ['youtube','135']].forEach(function (item) {
                var latency = document.getElementById('latency-' + item[0]);
                var dot = document.getElementById('dot-' + item[0]);
                if (latency) latency.textContent = item[1];
                if (dot) { dot.classList.remove('testing'); dot.classList.add('success'); dot.title = '本地模拟'; }
            });
            if (window.SettingsManager) {
                window.switch_run_mode = function (value) {
                    return window.SettingsManager.switchSetting('run_mode', value, '/local-preview');
                };
                window.switch_rule_mode = function (value) {
                    return window.SettingsManager.switchSetting('rule_mode', value, '/local-preview');
                };
                window.switch_oc_setting_oversea = function (value) {
                    return window.SettingsManager.switchSetting('oversea', value, '/local-preview');
                };
                window.switch_meta_sniffer = function (value) {
                    return window.SettingsManager.switchSetting('meta_sniffer', value, '/local-preview');
                };
                window.switch_respect_rules = function (value) {
                    return window.SettingsManager.switchSetting('respect_rules', value, '/local-preview');
                };
                window.switch_stream_unlock = function (value) {
                    return window.SettingsManager.switchSetting('stream_unlock', value, '/local-preview');
                };
            }
            ['togglePlugin','restartCore','editOverwrite','toggleThemeMode','winOpen','switch_run_mode','switch_rule_mode',
             'switch_oc_setting_oversea','switch_meta_sniffer','switch_respect_rules','switch_stream_unlock','refreshSubscriptionInfo',
             'setSubscriptionUrl','switchConfig','updateConfig','editConfig','editSubscribe','uploadConfig','copyAddress','copySecret',
             'copyMixAddress','generatePacConfig','copyMixAuth','ycad_dashboard','net_dashboard','meta_dashboard','net_zashboard',
             'b_close_all_connection','b_reload_firewall','b_flush_dns_cache','all_one_key_update','privacy_my_ip','toggle_mode_by_icon',
             'refresh_myip','ip_skk'].forEach(function (name) {
                if (!window[name]) window[name] = function () { return false; };
            });
            var preview = window.openkillPreview || { actions: [], requests: [] };
            preview.setState = setState;
            preview.settings = window.SettingsManager || null;
            preview.configManager = window.ConfigFileManager || null;
            window.openkillPreview = preview;
            document.addEventListener('click', function (event) {
                var control = event.target.closest('button, input[type="button"], .icon-btn, .myip-icon-btn');
                if (!control) return;
                var id = control.id || control.getAttribute('title') || 'anonymous-control';
                window.openkillPreview.actions.push(id);
                if (control.matches('.dashboard-btn, .action-btn, .copy-btn')) {
                    event.preventDefault();
                    event.stopPropagation();
                }
            }, true);
            document.querySelectorAll('[data-preview-state]').forEach(function (control) {
                control.addEventListener('click', function () { setState(control.dataset.previewState); });
            });
            setState('running');
        })();
"""


PREVIEW_PRODUCTION_BOOTSTRAP = r"""
        (function () {
            var byId = function (id) { return document.getElementById(id); };
            var names = function (name) { return document.getElementsByName(name); };
            window.openkillPreview = window.openkillPreview || { actions: [], requests: [] };
            var preview = window.openkillPreview;
            var DOMCache = {
                meta_sniffer_on: byId('meta_sniffer_on'),
                meta_sniffer_off: byId('meta_sniffer_off'),
                respect_rules_on: byId('respect_rules_on'),
                respect_rules_off: byId('respect_rules_off'),
                oc_setting_oversea_0: byId('oc_setting_oversea_0'),
                oc_setting_oversea_1: byId('oc_setting_oversea_1'),
                oc_setting_oversea_2: byId('oc_setting_oversea_2'),
                stream_unlock_on: byId('stream_unlock_on'),
                stream_unlock_off: byId('stream_unlock_off'),
                radio: names('radios'),
                radio_ru: names('radios-ru')
            };
            var XHR = {
                get: function (endpoint, params, callback) {
                    preview.requests.push({ endpoint: endpoint, params: params });
                    setTimeout(function () { callback({ status: 200 }, {}); }, 0);
                }
            };
            window.DOMCache = DOMCache;
            window.XHR = XHR;
            window.openkillPreview.settingsDomCache = DOMCache;
            window.openkillPreview.settingsXHR = XHR;
        })();
"""


PREVIEW_CONFIG_BOOTSTRAP = r"""
        var ocFormatUnixTime = function (value) { return String(value || ''); };
        var ocFormatFileSize = function (value) { return String(value || ''); };
        var StateManager = { cachedXHRGet: function () {}, cachedXHRGetWithParams: function () {} };
        var SubscriptionManager = { currentConfigFile: '', getSubscriptionInfo: function () {} };
        var OverwriteSubscribeManager = { data: {}, render: function () {} };
"""


def build_preview(output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    html = """<!doctype html>
<html data-darkmode="true" lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>OpenKill 运行状态 · 本地模拟</title>
  <link rel="stylesheet" href="/luci-app-openkill/root/www/luci-static/resources/openkill/css/oc.css?v=local-preview">
  <link rel="stylesheet" href="/luci-app-openkill/root/www/luci-static/resources/openkill/css/flat.css?v=local-preview">
  <style>__PREVIEW_STYLE__</style>
</head>
<body data-page="admin-services-openkill-client">
  <div class="openkill-preview-banner" role="note">
    <span><strong>本地模拟</strong> · 使用生产模板与样式，不连接设备、不发起外部请求。</span>
    <span class="openkill-preview-controls" aria-label="模拟运行状态">
      <button type="button" data-preview-state="running">运行中</button>
      <button type="button" data-preview-state="stopped">已停止</button>
      <button type="button" data-preview-state="disabled">已禁用</button>
      <button type="button" data-preview-state="startup_failed">启动失败</button>
      <button type="button" data-preview-state="loading">加载中</button>
      <button type="button" data-preview-state="unknown">未知</button>
      <button type="button" data-preview-state="error">错误</button>
    </span>
  </div>
  <main class="openkill-preview-page" data-preview-fixture="local-only">
    __STATUS__
    __MYIP__
  </main>
  <script src="/luci-app-openkill/root/www/luci-static/resources/openkill/js/oc-icons.js"></script>
  <script src="/luci-app-openkill/root/www/luci-static/resources/openkill/js/common.js"></script>
  <script>__PREVIEW_CONFIG_BOOTSTRAP__</script>
  <script>__PRODUCTION_STATUS_VISIBILITY_HELPER__</script>
  <script>__PRODUCTION_CONFIG_UPLOADER__</script>
  <script>__PRODUCTION_CONFIG_EDITOR__</script>
  <script>__PRODUCTION_CONFIG_FILE_MANAGER__</script>
  <script>__PREVIEW_PRODUCTION_BOOTSTRAP__</script>
  <script>__PRODUCTION_SETTINGS_MANAGER__</script>
  <script>__PREVIEW_SCRIPT__</script>
</body>
</html>
"""
    html = html.replace("__PREVIEW_STYLE__", PREVIEW_STYLE.strip())
    html = html.replace("__PREVIEW_SCRIPT__", PREVIEW_SCRIPT.strip())
    html = html.replace("__PREVIEW_CONFIG_BOOTSTRAP__", PREVIEW_CONFIG_BOOTSTRAP.strip())
    html = html.replace("__PRODUCTION_STATUS_VISIBILITY_HELPER__", _extract_status_visibility_helper())
    html = html.replace("__PRODUCTION_CONFIG_UPLOADER__", _extract_config_uploader())
    html = html.replace("__PRODUCTION_CONFIG_EDITOR__", _extract_config_editor())
    html = html.replace("__PRODUCTION_CONFIG_FILE_MANAGER__", _extract_config_file_manager())
    html = html.replace("__PREVIEW_PRODUCTION_BOOTSTRAP__", PREVIEW_PRODUCTION_BOOTSTRAP.strip())
    html = html.replace("__PRODUCTION_SETTINGS_MANAGER__", _extract_settings_manager())
    html = html.replace("__STATUS__", _extract_status())
    html = html.replace("__MYIP__", _extract_myip())
    target = output / "index.html"
    target.write_text(html, encoding="utf-8", newline="\n")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="directory for the generated preview")
    args = parser.parse_args()
    print(build_preview(args.output.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
