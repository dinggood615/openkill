#!/usr/bin/env python3
"""Local, record-only comparison of production firewall intent and NFT IR.

This module is deliberately a development tool.  It extracts the *current*
production shell function bodies from the checked-out source, hashes those
bodies, and runs them in a disposable Bash process whose command surface is
made entirely of record-only stubs.  No OpenWrt service, UCI database,
network command, nftables ruleset, or iptables ruleset is touched.

The recorder is intentionally small: it captures the modern ``nft`` command
language emitted by ``set_firewall`` and ``apply_node_endpoint_sets`` and
normalizes the resulting add/insert/flush sequence into a final intent.  The
normalizer is independent of the central classifier and renderer; semantic
expectations come from the separately-audited current-intent fixture.
"""

from __future__ import annotations

import hashlib
import copy
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import tempfile
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from openkill_nft_ir import render_context, render_state
from openkill_nft_syntax import UnsupportedNftAction, lower_nft_ir, render_nft
from openkill_shadow_adapter import adapt, normalize_state, shadow_compare, validate_intent_fixture


PHASE_3C_SCHEMA = "OPENKILL_PRODUCTION_SHADOW_V1"
CURRENT_PROFILE = "current"
PRODUCTION_PATHS = {
    "init": pathlib.Path("luci-app-openkill/root/etc/init.d/openkill"),
    "network": pathlib.Path("luci-app-openkill/root/usr/share/openkill/openkill_network.sh"),
}
FUNCTION_SOURCES = {
    "set_firewall": "init",
    "apply_node_endpoint_sets": "init",
    "fw4_has_dns_hijack_rule": "init",
    "fw4_dns_hijack_ready": "init",
    "load_ip_route_pass": "init",
    "change_dnsmasq": "init",
    "openkill_render_dns_set_rules": "network",
    "openkill_classifier_match": "network",
    "openkill_render_classifier_rule": "network",
}
FUNCTION_END_MARKERS = {
    "set_firewall": "\nrevert_firewall()",
    "apply_node_endpoint_sets": "\nset_firewall()",
    "fw4_has_dns_hijack_rule": "\nfw4_dns_hijack_ready()",
    "fw4_dns_hijack_ready": "\nensure_fw4_dns_hijack()",
    "load_ip_route_pass": "\nchange_dnsmasq()",
    "change_dnsmasq": "\nrevert_dnsmasq()",
    "openkill_render_dns_set_rules": "\nopenkill_owner_actions()",
    "openkill_classifier_match": "\nopenkill_nft_string_quote()",
    "openkill_render_classifier_rule": "\nopenkill_render_dns_set_rules()",
}

COMMAND_ALLOWLIST = frozenset(
    {
        "nft",
        "iptables",
        "ip6tables",
        "ipset",
        "uci",
        "ip",
        "fw4",
        "logger",
        "service",
        "kill",
        "pkill",
        "rm",
        "cp",
        "mv",
        "chmod",
        "chown",
        "mkdir",
        "cat",
        "grep",
        "awk",
        "sed",
        "sort",
        "tr",
        "head",
        "tail",
        "sleep",
        "dnsmasq",
        "netstat",
        "nslookup",
        "mktemp",
        "dirname",
        "touch",
    "crontab",
    "printf",
    }
)

MISMATCH_CLASSES = frozenset(
    {
        "OLD_HARNESS_DEFECT",
        "OLD_NORMALIZER_DEFECT",
        "NEW_RENDERER_DEFECT",
        "IR_DEFECT",
        "SEMANTIC_SPEC_DEFECT",
        "KNOWN_CURRENT_GAP",
        "UNSUPPORTED_CURRENT_CASE",
        "APPROVED_STRUCTURAL_EQUIVALENCE",
        "UNKNOWN",
    }
)


class ProductionShadowError(RuntimeError):
    """A fail-closed production-source or harness error."""


def _repo_root(root: Optional[pathlib.Path] = None) -> pathlib.Path:
    return pathlib.Path(root or pathlib.Path(__file__).resolve().parents[1]).resolve()


def _read_source(root: pathlib.Path, source_key: str) -> Tuple[pathlib.Path, str]:
    path = _repo_root(root) / PRODUCTION_PATHS[source_key]
    try:
        return path, path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ProductionShadowError("cannot read production source {}: {}".format(path, exc)) from exc


def extract_shell_function(source: str, name: str, *, end_marker: Optional[str] = None) -> str:
    """Extract an exact function slice without executing the shell file.

    The production files contain shell brace expansion and parameter braces,
    so a generic brace counter is intentionally not used as the primary
    boundary detector.  Stable neighbouring function markers provide a much
    safer boundary; a conservative lexical fallback is retained for future
    source movement and fails closed when it cannot prove a boundary.
    """

    match = re.search(r"(?m)^{}\s*\(\)\s*\{{".format(re.escape(name)), source)
    if not match:
        raise ProductionShadowError("production function not found: {}".format(name))
    start = match.start()
    marker = end_marker or FUNCTION_END_MARKERS.get(name)
    if marker:
        end = source.find(marker, match.end())
        if end >= 0:
            return source[start:end]

    # Fallback scanner: ignore quoted strings/comments and parameter braces.
    opening = source.find("{", match.end() - 1)
    depth = 0
    quote: Optional[str] = None
    escaped = False
    comment = False
    parameter_depth = 0
    i = opening
    while i < len(source):
        char = source[i]
        if comment:
            if char == "\n":
                comment = False
        elif escaped:
            escaped = False
        elif char == "\\" and quote != "'":
            escaped = True
        elif quote:
            if char == quote:
                quote = None
        elif char in {"'", '"'}:
            quote = char
        elif char == "#" and (i == 0 or source[i - 1] in " \t\n"):
            comment = True
        elif char == "$" and i + 1 < len(source) and source[i + 1] == "{":
            parameter_depth += 1
            i += 1
        elif parameter_depth:
            if char == "}":
                parameter_depth -= 1
        elif char == "{":
            # Shell brace expansion (for example {tcp,udp}) is not a code
            # block.  It has no whitespace-delimited ``{`` in the production
            # function's function blocks.
            if i == opening or source[i - 1].isspace() or source[i - 1] == ";":
                depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
        i += 1
    raise ProductionShadowError("unable to prove end of production function: {}".format(name))


def production_function_hashes(root: Optional[pathlib.Path] = None) -> Dict[str, Dict[str, Any]]:
    """Return auditable hashes for every production function used by 3C."""

    root_path = _repo_root(root)
    result: Dict[str, Dict[str, Any]] = {}
    for name, source_key in FUNCTION_SOURCES.items():
        path, source = _read_source(root_path, source_key)
        function = extract_shell_function(source, name)
        result[name] = {
            "path": str(PRODUCTION_PATHS[source_key]).replace("\\", "/"),
            "sha256": hashlib.sha256(function.encode("utf-8")).hexdigest(),
            "bytes": len(function.encode("utf-8")),
        }
    return result


def _linux_path(path: pathlib.Path) -> str:
    """Convert a Windows path to a WSL path for the checked-in Bash tool."""

    resolved = pathlib.Path(path).resolve()
    drive = resolved.drive.rstrip(":").lower()
    if drive and resolved.root:
        tail = str(resolved)[len(resolved.drive) :].replace("\\", "/")
        return "/mnt/{}/{}".format(drive, tail.lstrip("/"))
    return str(resolved).replace("\\", "/")


def _shell_quote(value: Any) -> str:
    return shlex.quote(str(value))


def _state_values(state: Mapping[str, Any], packet: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Map a normalized state into the variables consumed by set_firewall."""

    normalized = normalize_state(state)
    v6 = any(normalized.get(key) for key in ("wan6", "node6", "local6", "lan6", "delegated6", "china6", "china_pass6", "fake_ip6", "user_direct6", "user_proxy6", "access6"))
    if packet and str(packet.get("family", "")).upper() in {"IPV6", "6"}:
        v6 = True
    scope = normalized.get("dns_scope", "NONE")
    mode = normalized.get("run_mode", "TUN")
    if mode == "TUN":
        ipv6_mode = 2
        en_mode_tun: Any = 1
    elif mode == "TPROXY":
        ipv6_mode = 0
        en_mode_tun = ""
    else:
        ipv6_mode = 1
        en_mode_tun = ""
    china_policy = normalized.get("china_policy", "OFF")
    if china_policy in {"BYPASS_MAINLAND", "MAINLAND", "1"}:
        china_v4, china_v6 = 1, 1
    elif china_policy in {"BYPASS_OVERSEAS", "OVERSEAS", "2"}:
        china_v4, china_v6 = 2, 2
    else:
        china_v4 = china_v6 = 0
    # The production switch is numeric: mode 1 is direct LAN (plus optional
    # router-self) hijack, mode 2 is the shared redirect chain used by the
    # LAN-and-router scope.  Keep ROUTER_ONLY on mode 1 with the explicit
    # router_self_proxy gate.
    default_dns_mode = "2" if scope == "LAN_AND_ROUTER" else ("1" if scope in {"LAN", "ROUTER_ONLY"} else "0")
    dns_mode = str(state.get("dns_mode", default_dns_mode))
    fake4 = normalized.get("fake_ip4") or ["198.18.0.0/15"]
    fake6 = normalized.get("fake_ip6") or ["fd00:ffff::/96"]
    # Values are all fixture data and are quoted again by the harness before
    # insertion into Bash.  The renderer still receives the original state.
    return {
        "tun_owner": normalized["owner"].lower(),
        "ipv6_enable": 1 if v6 or normalized.get("id", "").endswith("V6") else 0,
        "ipv6_dns": 1 if v6 else 0,
        "ipv6_mode": ipv6_mode,
        "en_mode_tun": en_mode_tun,
        # OpenKill's production UCI default is fake-ip-tun.  A state fixture
        # may override ``en_mode`` explicitly; absent that field retain the
        # default rather than inferring mode from whether a synthetic packet
        # range was included in the fixture.
        "en_mode": str(state.get("en_mode", "fake-ip" if mode == "TUN" else "redir-host")),
        "enable_redirect_dns": dns_mode,
        "china_ip_route": china_v4,
        "china_ip6_route": china_v6,
        "disable_udp_quic": 0,
        "lan_ac_mode": 1 if any(e.get("action") == "ALLOW" for e in normalized.get("access4", ()) + normalized.get("access6", ())) else 0,
        "common_ports": 0,
        "router_self_proxy": 1 if normalized.get("router_self_proxy") else 0,
        "bypass_gateway_compatible": 0,
        "intranet_allowed": 0,
        "enable_udp_proxy": 1 if mode == "TPROXY" else 0,
        "enable_v6_udp_proxy": 1 if mode == "TPROXY" else 0,
        "wan_ip4s": " ".join(normalized.get("wan4", ())),
        "wan_ip6s": " ".join(normalized.get("wan6", ())),
        "fakeip_range": " ".join(fake4),
        "fakeip_range6": " ".join(fake6),
        "service_ports": " ".join(str(item) for item in normalized.get("service_ports", ())),
        "dns_scope": scope,
        "lan_ac_black_ips": " ".join(e["network"] for e in normalized.get("access4", ()) if e.get("action") == "DENY"),
        "lan_ac_black_ipv6s": " ".join(e["network"] for e in normalized.get("access6", ()) if e.get("action") == "DENY"),
        "lan_ac_white_ips": " ".join(e["network"] for e in normalized.get("access4", ()) if e.get("action") == "ALLOW"),
        "lan_ac_white_ipv6s": " ".join(e["network"] for e in normalized.get("access6", ()) if e.get("action") == "ALLOW"),
        "node4": " ".join(normalized.get("node4", ())),
        "node6": " ".join(normalized.get("node6", ())),
        "china4": " ".join(normalized.get("china4", ())),
        "china6": " ".join(normalized.get("china6", ())),
        "china_pass4": " ".join(normalized.get("china_pass4", ())),
        "china_pass6": " ".join(normalized.get("china_pass6", ())),
        "user_direct4": " ".join(normalized.get("user_direct4", ())),
        "user_direct6": " ".join(normalized.get("user_direct6", ())),
        "user_proxy4": " ".join(normalized.get("user_proxy4", ())),
        "user_proxy6": " ".join(normalized.get("user_proxy6", ())),
    }


def _stub_header(values: Mapping[str, Any], sandbox: str, *, node_apply: bool = False) -> str:
    """Build the fail-closed Bash harness prelude."""

    cfg = {
        key: values.get(key, "")
        for key in (
            "lan_ac_black_ips",
            "lan_ac_black_ipv6s",
            "lan_ac_white_ips",
            "lan_ac_white_ipv6s",
            "node4",
            "node6",
            "china4",
            "china6",
            "china_pass4",
            "china_pass6",
            "user_direct4",
            "user_direct6",
            "user_proxy4",
            "user_proxy6",
        )
    }
    lines = [
        "set +e",
        "SANDBOX={}".format(_shell_quote(sandbox)),
        "LOG=\"$SANDBOX/commands.log\"",
        "UNKNOWN_LOG=\"$SANDBOX/unknown.log\"",
        "command mkdir -p \"$SANDBOX\" \"$SANDBOX/etc-openkill\"",
        "record(){ command printf '%s\\t%s\\n' \"$1\" \"$*\" >> \"$LOG\"; }",
        "unknown(){ command printf '%s\\n' \"$*\" >> \"$UNKNOWN_LOG\"; UNKNOWN_COUNT=$((UNKNOWN_COUNT+1)); return 127; }",
        "command_not_found_handle(){ unknown \"$@\"; }",
        # Every external command used by the production body is a stub.  The
        # only filesystem operations allowed here are under SANDBOX.
        # Read-only discovery commands are intentionally not appended to the
        # shared log.  They often run on the two sides of a shell pipeline
        # concurrently (for example ``nft list chain | grep``); DrvFS does
        # not guarantee atomic append for those concurrent writers and can
        # corrupt a diagnostic line.  Their status is still deterministic,
        # while all mutating intent commands remain recorded below.
        "nft(){ case \"$*\" in list\\ chain*) return 0;; list\\ sets*|list\\ table*) return 1;; esac; record nft \"$@\"; return 0; }",
        "iptables(){ record iptables \"$@\"; return 1; }",
        "ip6tables(){ record ip6tables \"$@\"; return 1; }",
        "ipset(){ record ipset \"$@\"; return 0; }",
        "uci(){ record uci \"$@\"; case \"$*\" in *'dhcp.@dnsmasq[0].port'*) printf '7874';; *get*|*show*) return 1;; esac; return 0; }",
        "ip(){ record ip \"$@\"; return 0; }",
        "fw4(){ record fw4 \"$@\"; return 0; }",
        "logger(){ record logger \"$@\"; return 0; }",
        "service(){ record service \"$@\"; return 0; }",
        "kill(){ record kill \"$@\"; return 0; }",
        "pkill(){ record pkill \"$@\"; return 0; }",
        "rm(){ record rm \"$@\"; return 0; }",
        "cp(){ record cp \"$@\"; return 0; }",
        "mv(){ record mv \"$@\"; return 0; }",
        "chmod(){ record chmod \"$@\"; return 0; }",
        "chown(){ record chown \"$@\"; return 0; }",
        "mkdir(){ record mkdir \"$@\"; case \"$1\" in \"$SANDBOX\"/*|\"$SANDBOX\") command mkdir -p \"$@\";; *) return 1;; esac; }",
        "cat(){ record cat \"$@\"; for item in \"$@\"; do case \"$item\" in \"$SANDBOX\"/*) command cat \"$item\";; *) return 1;; esac; done; }",
        "grep(){ record grep \"$@\"; while IFS= read -r _line; do :; done; return 1; }",
        "awk(){ record awk \"$@\"; while IFS= read -r _line; do :; done; return 1; }",
        "sed(){ record sed \"$@\"; while IFS= read -r _line; do :; done; return 1; }",
        "sort(){ record sort \"$@\"; while IFS= read -r _line; do :; done; return 0; }",
        "tr(){ record tr \"$@\"; while IFS= read -r _line; do :; done; return 0; }",
        "head(){ record head \"$@\"; while IFS= read -r _line; do :; done; return 0; }",
        "tail(){ record tail \"$@\"; while IFS= read -r _line; do :; done; return 0; }",
        "sleep(){ return 0; }",
        "dnsmasq(){ record dnsmasq \"$@\"; return 1; }",
        "netstat(){ record netstat \"$@\"; return 1; }",
        "nslookup(){ record nslookup \"$@\"; return 1; }",
        "mktemp(){ local p=\"$SANDBOX/mktemp.$RANDOM\"; : > \"$p\"; printf '%s\\n' \"$p\"; }",
        "dirname(){ printf '%s\\n' \"$SANDBOX\"; }",
        "touch(){ for item in \"$@\"; do case \"$item\" in \"$SANDBOX\"/*) : > \"$item\";; *) return 1;; esac; done; }",
        "crontab(){ record crontab \"$@\"; return 0; }",
        "check_mod(){ return 0; }",
        "start_fail(){ return 1; }",
        "LOG_TIP(){ :; }; LOG_WARN(){ :; }; LOG_ERROR(){ :; }; LOG_OUT(){ :; }",
        "prepare_openkill_include(){ :; }",
        "openkill_render_nft_set_update_batch(){ return 1; }",
        "openkill_validate_nft_batch(){ return 1; }",
        "openkill_render_nft_set_batch(){ return 1; }",
        "openkill_remove_proxy_runtime(){ return 0; }",
        "openkill_current_start(){ return 0; }",
        "openkill_node_dns_servers(){ return 1; }",
        "fw4_has_dns_hijack_rule(){ return 1; }",
        "fw4_dns_hijack_ready(){ return 0; }",
        "upnp_exclude(){ :; }",
        "config_load(){ return 0; }",
        "config_foreach(){ return 0; }",
        "wan_name_add(){ :; }; wan6_name_add(){ :; }",
        "uci_get_config(){ case \"$1\" in remote_service_bypass) printf '1';; remote_service_ports) printf '%s' "
        + _shell_quote(values.get("service_ports", ""))
        + ";; lan_ac_black_ips) printf '%s' \"$CFG_lan_ac_black_ips\";; lan_ac_black_ipv6s) printf '%s' \"$CFG_lan_ac_black_ipv6s\";; lan_ac_white_ips) printf '%s' \"$CFG_lan_ac_white_ips\";; lan_ac_white_ipv6s) printf '%s' \"$CFG_lan_ac_white_ipv6s\";; *) printf ''; esac; }",
        "config_list_foreach(){ local _section=\"$1\" _list=\"$2\" _cb=\"$3\"; shift 3; local _vals=\"\"; case \"$_list\" in lan_ac_black_ips) _vals=\"$CFG_lan_ac_black_ips\";; lan_ac_black_ipv6s) _vals=\"$CFG_lan_ac_black_ipv6s\";; lan_ac_white_ips) _vals=\"$CFG_lan_ac_white_ips\";; lan_ac_white_ipv6s) _vals=\"$CFG_lan_ac_white_ipv6s\";; esac; for _v in $_vals; do \"$_cb\" \"$_v\" \"$@\"; done; }",
        "nft_ac_add(){ [ -n \"$1\" ] || return 0; nft add element inet fw4 \"$2\" { \"$1\" }; [ -n \"$3\" ] && nft add element inet fw4 \"$3\" { \"$1\" }; }",
    ]
    if node_apply:
        lines.extend(
            [
                "openkill_extract_node_endpoints(){ return 0; }",
                "openkill_refresh_node_endpoints(){ printf '%s\\n' \"$CFG_node4\" > \"$4\"; printf '%s\\n' \"$CFG_node6\" > \"$5\"; return 0; }",
                # The exact production classifier-match and rule-builder
                # bodies are appended by run_production_harness below.  This
                # quote helper is deliberately shell-builtin-only so the
                # extracted rule builder cannot escape the sandbox through a
                # sed/printf subprocess.
                "openkill_nft_string_quote(){ printf '\"%s\"' \"$1\"; }",
            ]
        )
    else:
        lines.append("apply_node_endpoint_sets(){ record INTERNAL apply_node_endpoint_sets; return 0; }")
    lines.extend(
        [
            "FW4=/usr/sbin/fw4",
            "PROXY_FWMARK=0x162; PROXY_ROUTE_TABLE=354",
            "proxy_port=7892; tproxy_port=7893; dns_port=7874; DNSPORT=7874",
            "wan_int=wan; wan6_int=wan6; wan_ints=wan; wan6_ints=wan6",
            "upnp_lease_file=\"$SANDBOX/upnp\"",
            "CONFIG_FILE=\"$SANDBOX/config.yaml\"; : > \"$CONFIG_FILE\"",
            "OPENKILL_NFT_BATCH=0",
            "UNKNOWN_COUNT=0",
        ]
    )
    for key, value in values.items():
        if key in {"dns_scope", "service_ports"}:
            continue
        lines.append("{}={}".format(key, _shell_quote(value)))
    for key, value in cfg.items():
        lines.append("CFG_{}={}".format(key, _shell_quote(value)))
    # Production source uses an absolute resolver helper.  Point only the
    # extracted body at a harmless fixture executable inside the sandbox.
    return "\n".join(lines) + "\n"


def _prepare_source_body(body: str, sandbox: str) -> str:
    transformed = body.replace("/tmp/", "${SANDBOX}/")
    transformed = transformed.replace("/etc/openkill/", "${SANDBOX}/etc-openkill/")
    transformed = transformed.replace("/usr/share/openkill/openkill_get_network.lua", "${SANDBOX}/get_network.lua")
    # The generated script is always fed with LF; source hashes use the
    # original bytes above and therefore remain drift-detectable.
    return transformed.replace("\r\n", "\n").replace("\r", "\n")


def _fixture_files(values: Mapping[str, Any], sandbox: pathlib.Path) -> None:
    etc = sandbox / "etc-openkill"
    etc.mkdir(parents=True, exist_ok=True)
    for name, key in (("china_ip_route.ipset", "china4"), ("china_ip6_route.ipset", "china6")):
        family = "ipv4_addr" if key == "china4" else "ipv6_addr"
        values_list = str(values.get(key, "")).split()
        set_name = "china_ip_route" if key == "china4" else "china_ip6_route"
        lines = ["add set inet fw4 {} {{ type {}; flags interval; auto-merge; }}".format(set_name, family)]
        if values_list:
            lines.append("add element inet fw4 {} {{ {} }}".format(set_name, ", ".join(values_list)))
        (etc / name).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    for name, key, family in (
        ("openkill_china_ip_route_pass.list", "china_pass4", "ipv4_addr"),
        ("openkill_china_ip6_route_pass.list", "china_pass6", "ipv6_addr"),
    ):
        values_list = str(values.get(key, "")).split()
        set_name = name.rsplit(".", 1)[0]
        lines = ["add set inet fw4 {} {{ type {}; flags interval; auto-merge; }}".format(set_name, family)]
        if values_list:
            lines.append("add element inet fw4 {} {{ {} }}".format(set_name, ", ".join(values_list)))
        (sandbox / name).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    get_network = sandbox / "get_network.lua"
    get_network.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8", newline="\n")
    try:
        get_network.chmod(0o700)
    except OSError:
        pass


def run_production_harness(
    state: Mapping[str, Any],
    *,
    function: str = "set_firewall",
    packet: Optional[Mapping[str, Any]] = None,
    root: Optional[pathlib.Path] = None,
) -> Dict[str, Any]:
    """Run one extracted production function with record-only commands."""

    if function not in {"set_firewall", "apply_node_endpoint_sets"}:
        raise ProductionShadowError("unsupported harness function: {}".format(function))
    root_path = _repo_root(root)
    values = _state_values(state, packet)
    path, source = _read_source(root_path, "init")
    body = extract_shell_function(source, function)
    expected_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    temp = tempfile.mkdtemp(prefix="openkill-3c-")
    sandbox = pathlib.Path(temp)
    try:
        _fixture_files(values, sandbox)
        use_node_impl = function == "apply_node_endpoint_sets" or (
            function == "set_firewall" and values.get("tun_owner") == "openkill"
        )
        script = _stub_header(values, _linux_path(sandbox), node_apply=use_node_impl)
        # ``set_firewall`` invokes the production node endpoint updater at
        # the end of its modern path.  Include that exact function body in
        # the sandbox so the old intent contains the same dynamic node sets
        # and endpoint-protection rules; the helper commands remain stubs.
        if function == "set_firewall" and values.get("tun_owner") == "openkill":
            node_body = extract_shell_function(source, "apply_node_endpoint_sets")
            _, network_source = _read_source(root_path, "network")
            classifier_match_body = extract_shell_function(network_source, "openkill_classifier_match")
            classifier_rule_body = extract_shell_function(network_source, "openkill_render_classifier_rule")
            script += _prepare_source_body(classifier_match_body, _linux_path(sandbox)) + "\n"
            script += _prepare_source_body(classifier_rule_body, _linux_path(sandbox)) + "\n"
            script += _prepare_source_body(node_body, _linux_path(sandbox)) + "\n"
        script += _prepare_source_body(body, _linux_path(sandbox)) + "\n"
        script += "{}\nrc=$?\ncommand printf 'RC=%s\\n' \"$rc\"\ncommand printf 'UNKNOWN=%s\\n' \"$UNKNOWN_COUNT\"\n".format(function)
        bash = shutil.which("bash") or shutil.which("wsl")
        if not bash:
            raise ProductionShadowError("Bash is unavailable for the isolated production harness")
        # Windows' WSL launcher can translate text-mode stdin to CRLF.  Feed
        # bytes explicitly so the extracted POSIX shell remains LF-only.
        result = subprocess.run(
            [bash, "-s", "--", _linux_path(sandbox)],
            input=script.encode("utf-8"),
            text=False,
            capture_output=True,
            cwd=str(root_path),
            timeout=30,
            check=False,
        )
        stdout = result.stdout.decode("utf-8", "replace")
        stderr = result.stderr.decode("utf-8", "replace")
        commands_path = sandbox / "commands.log"
        unknown_path = sandbox / "unknown.log"
        commands = commands_path.read_text(encoding="utf-8").splitlines() if commands_path.exists() else []
        unknown = unknown_path.read_text(encoding="utf-8").splitlines() if unknown_path.exists() else []
        file_records: Dict[str, List[str]] = {}
        for fixture_path in sandbox.rglob("*"):
            if fixture_path.is_file() and fixture_path.name not in {"commands.log", "unknown.log"}:
                fixture_lines = _records_from_file(fixture_path)
                file_records[str(fixture_path)] = fixture_lines
                file_records[_linux_path(fixture_path)] = fixture_lines
                file_records["${SANDBOX}/" + str(fixture_path.relative_to(sandbox)).replace("\\", "/")] = fixture_lines
        rc_match = re.search(r"(?:^|\n)RC=(-?\d+)", stdout)
        rc = int(rc_match.group(1)) if rc_match else result.returncode
        return {
            "function": function,
            "source_path": str(path),
            "function_sha256": expected_hash,
            "returncode": rc,
            "process_returncode": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "command_records": commands,
            "unknown_commands": unknown,
            "file_records": file_records,
            "sandbox": str(sandbox),
            "state_id": normalize_state(state)["id"],
            "real_mutation": False,
        }
    finally:
        # The shell body itself is forbidden from deleting anything outside
        # SANDBOX.  Python removes this disposable directory after capture.
        import shutil as _shutil

        _shutil.rmtree(sandbox, ignore_errors=True)


def _split_record(line: str) -> Optional[Tuple[str, str]]:
    if "\t" not in line:
        return None
    kind, command = line.split("\t", 1)
    return kind.strip(), command.strip()


def _tokens(command: str) -> List[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        # Recorder text is diagnostics; malformed shell-like text must fail
        # closed instead of being guessed into a policy rule.
        return []


def _family_for_type(type_name: str) -> str:
    value = type_name.lower().rstrip(";," )
    if "ipv6" in value:
        return "IPv6"
    if "ipv4" in value:
        return "IPv4"
    return "ALL"


def _semantic_reason(expression: str) -> Optional[str]:
    lower = expression.lower()
    if "dport 53" in lower or "dns hijack" in lower or "dns_redirect" in lower:
        return "DNS"
    if re.search(r"(?:ip|ip6) daddr \{[^}]+\}.*mark set 0x162", lower):
        return "FAKEIP"
    if "skgid" in lower or "skuid" in lower:
        return "SELF_TRAFFIC"
    if "iifname utun" in lower:
        return "TUN_INGRESS"
    if "openkill_node4" in lower or "openkill_node6" in lower:
        return "NODE_ENDPOINT"
    if "localnetwork" in lower or "localnetwork6" in lower:
        return "LOCAL_DESTINATION"
    if "ct direction reply" in lower or "ctdir reply" in lower:
        return "REPLY_TRAFFIC"
    if "openkill_service_ports" in lower or "service_ports" in lower:
        return "SERVICE_PORT"
    if any(token in lower for token in ("lan_ac_", "wan_ac_", "openkill_access")):
        return "ACCESS_CONTROL"
    if any(token in lower for token in ("198.18.", "fd00:ffff", "fakeip")):
        return "FAKEIP"
    # A route rule with the primary China set plus an exclusion for the pass
    # set is still the CHINA_POLICY branch; the pass set is a guard/fallthrough
    # refinement rather than the selected reason.  A standalone pass-set
    # reference remains CHINA_PASS.
    if ("china_ip_route" in lower or "china_ip6_route" in lower) and "china_ip_route_pass" not in lower and "china_ip6_route_pass" not in lower:
        return "CHINA_POLICY"
    if "china_ip_route" in lower or "china_ip6_route" in lower:
        return "CHINA_POLICY" if re.search(r"@china_ip(?:6)?_route\b", lower) else "CHINA_PASS"
    return None


def _action_kind(expression: str) -> str:
    lower = expression.lower()
    if "dport 53" in lower and "redirect" in lower:
        return "DNS_REDIRECT"
    if "tproxy" in lower:
        return "TPROXY_PROXY"
    if "redirect to" in lower:
        return "REDIRECT_PROXY"
    if "mark set 0x162" in lower or "set-xmark 0x162" in lower:
        return "MARK_PROXY"
    if re.search(r"\bjump\s+\S+", lower):
        return "JUMP"
    if re.search(r"\breject\b", lower):
        return "ACCESS_DENY_REQUIRED"
    if re.search(r"\baccept\b", lower):
        return "ACCEPT_IF_REQUIRED"
    if re.search(r"\breturn\b", lower):
        return "RETURN_NATIVE"
    return "UNKNOWN_ACTION"


def _strip_punctuation(value: str) -> str:
    return value.strip("{};,\"'")


def _parse_one_nft(command: str, *, source: str = "command") -> Optional[Dict[str, Any]]:
    tokens = _tokens(command)
    if not tokens or tokens[0] != "nft":
        return None
    tokens = tokens[1:]
    if not tokens:
        return None
    if tokens[0] == "-f":
        return {"kind": "include", "path": _strip_punctuation(tokens[1]) if len(tokens) > 1 else "", "source": source}
    if tokens[0] not in {"add", "insert", "flush", "delete", "replace"}:
        return None
    operation = tokens[0]
    if len(tokens) < 5 or tokens[2] != "inet" or tokens[3] != "fw4":
        return None
    object_type = tokens[1]
    if operation == "flush" and object_type in {"chain", "set"}:
        return {"kind": "flush_{}".format(object_type), "name": _strip_punctuation(tokens[4]), "source": source}
    if object_type == "chain":
        name = _strip_punctuation(tokens[4])
        tail = " ".join(tokens[5:])
        return {
            "kind": "chain",
            "operation": operation,
            "name": name,
            "family": "ALL",
            "type": (re.search(r"\btype\s+(\w+)", tail) or [None, None])[1],
            "hook": (re.search(r"\bhook\s+(\w+)", tail) or [None, None])[1],
            "priority": (re.search(r"\bpriority\s+(-?\d+)", tail) or [None, None])[1],
            "source": source,
        }
    if object_type == "set":
        name = _strip_punctuation(tokens[4])
        tail = " ".join(tokens[5:])
        type_match = re.search(r"\btype\s+([\w:]+)", tail)
        type_name = type_match.group(1) if type_match else ""
        flags_match = re.search(r"\bflags\s+([^;}]*)", tail)
        flags = [_strip_punctuation(item) for item in (flags_match.group(1).split(",") if flags_match else []) if _strip_punctuation(item)]
        return {
            "kind": "set",
            "operation": operation,
            "name": name,
            "type": type_name,
            "family": _family_for_type(type_name),
            "flags": sorted(set(flags)),
            "source": source,
        }
    if object_type == "element":
        name = _strip_punctuation(tokens[4])
        values: List[str] = []
        if "{" in tokens:
            left = tokens.index("{") + 1
            right = tokens.index("}", left) if "}" in tokens[left:] else len(tokens)
            values = [_strip_punctuation(item) for item in tokens[left:right] if _strip_punctuation(item) not in {"", ","}]
        return {"kind": "element", "operation": operation, "name": name, "elements": values, "source": source}
    if object_type == "rule":
        # insert syntax includes ``position N`` between chain and expression.
        chain = _strip_punctuation(tokens[4])
        index = 5
        position: Optional[int] = None
        if operation == "insert" and index + 1 < len(tokens) and tokens[index] == "position":
            try:
                position = int(_strip_punctuation(tokens[index + 1]))
            except ValueError:
                position = None
            index += 2
        expression = " ".join(tokens[index:])
        return {
            "kind": "rule",
            "operation": operation,
            "chain": chain,
            "position": position,
            "expression": expression,
            "reason": _semantic_reason(expression),
            "action": _action_kind(expression),
            "source": source,
        }
    return None


def _records_from_file(path: pathlib.Path) -> List[str]:
    try:
        result = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            result.append("nft\t" + (line if line.startswith("nft ") else "nft " + line))
        return result
    except (OSError, UnicodeError):
        return []


def parse_nft_command_records(
    records: Sequence[str],
    *,
    sandbox: Optional[pathlib.Path] = None,
    file_records: Optional[Mapping[str, Sequence[str]]] = None,
) -> Dict[str, Any]:
    """Simulate final nft object state from record-only commands."""

    chains: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    sets: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    rules: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
    includes: List[str] = []
    expanded: List[str] = list(records)
    for line in records:
        parsed = _split_record(line)
        if not parsed:
            continue
        kind, command = parsed
        if kind != "nft":
            continue
        item = _parse_one_nft(command)
        if item and item.get("kind") == "include" and (sandbox or file_records):
            path_text = item.get("path", "")
            candidate = pathlib.Path(path_text)
            include_records: Optional[Sequence[str]] = None
            if file_records:
                include_records = file_records.get(path_text)
                if include_records is None and "${SANDBOX}" in path_text:
                    include_records = file_records.get(path_text.replace("${SANDBOX}", str(sandbox or "").rstrip("/\\")))
            if include_records is not None:
                includes.append(path_text)
                expanded.extend(include_records)
            elif candidate.exists():
                includes.append(path_text)
                expanded.extend(_records_from_file(candidate))
    for line in expanded:
        parsed = _split_record(line)
        if not parsed or parsed[0] != "nft":
            continue
        item = _parse_one_nft(parsed[1])
        if not item:
            continue
        kind = item["kind"]
        if kind == "chain":
            if item.get("operation") in {"add", "insert"}:
                chains[item["name"]] = item
                rules.setdefault(item["name"], [])
        elif kind == "set":
            if item.get("operation") in {"add", "insert"}:
                sets[item["name"]] = {**item, "elements": []}
        elif kind == "element":
            target = sets.setdefault(item["name"], {"name": item["name"], "elements": [], "family": "ALL", "type": "", "flags": []})
            if item.get("operation") in {"add", "insert"}:
                values = list(item.get("elements", ()))
                target["elements"] = sorted(set(target.get("elements", ())) | set(values))
        elif kind == "flush_chain":
            rules[item["name"]] = []
        elif kind == "flush_set":
            if item["name"] in sets:
                sets[item["name"]]["elements"] = []
        elif kind == "rule":
            chain = item["chain"]
            bucket = rules.setdefault(chain, [])
            if item.get("operation") == "insert":
                position = item.get("position")
                index = 0 if position in (None, 0) else max(0, position - 1)
                bucket.insert(index, item)
            elif item.get("operation") == "add":
                bucket.append(item)
    normalized_rules = []
    for chain, values in rules.items():
        for index, rule in enumerate(values):
            normalized_rules.append({**rule, "chain": chain, "order": index})
    owned_chains = [
        {**item, "owner": "OPENKILL", "ownership": "OWNED"}
        for name, item in chains.items()
        if name.startswith("openkill") or name == "nat_output"
    ]
    owned_sets = [
        {**item, "owner": "OPENKILL", "ownership": "OWNED"}
        for name, item in sets.items()
        if name.startswith(("openkill", "localnetwork", "china", "lan_ac_", "wan_ac_", "common_ports"))
    ]
    attachments = [item for item in normalized_rules if item["chain"] in {"dstnat", "mangle_prerouting", "mangle_output", "output", "srcnat", "input", "forward", "nat_output"} and item.get("action") == "JUMP"]
    return {
        "schema": "OPENKILL_OLD_NORMALIZED_INTENT_V1",
        "table": {"family": "inet", "name": "fw4", "owner": "FW4", "ownership": "REFERENCE_ONLY"},
        "chains": sorted(owned_chains, key=lambda item: item["name"]),
        "sets": sorted(owned_sets, key=lambda item: item["name"]),
        "rules": normalized_rules,
        "attachments": attachments,
        "includes": includes,
        "raw_record_count": len(records),
        "expanded_record_count": len(expanded),
        "normalizer": "record-only nft add/insert/flush simulator",
    }


def normalize_new_renderer_intent(state: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize the current renderer AST into the comparison vocabulary."""

    ir = render_state(state, profile=CURRENT_PROFILE, backend="ABSTRACT_NFT")
    ast = lower_nft_ir(ir)
    return {
        "schema": "OPENKILL_NEW_NORMALIZED_INTENT_V1",
        "table": ast["table"],
        "chains": [dict(item, name=item["physical_name"], owner="OPENKILL", ownership="OWNED") for item in ast.get("owned_chains", ())],
        "sets": [dict(item, name=item["physical_name"], owner="OPENKILL", ownership="OWNED") for item in ast.get("sets", ())],
        "rules": [dict(item, chain=item["chain"], reason=item.get("semantic_reason"), action=item.get("action_type"), order=index) for index, item in enumerate(ast.get("rules", ()))],
        "attachments": [dict(item, name=item["physical_name"], action=item.get("action_type")) for item in ast.get("attachments", ())],
        "ast": ast,
        "rendered_text": render_nft(ir),
    }


def normalize_new_context_intent(
    state: Mapping[str, Any], packet: Mapping[str, Any], *, profile: str = CURRENT_PROFILE
) -> Dict[str, Any]:
    """Normalize one packet-scoped renderer output for DNS/scope checks."""

    adapted = adapt(state, packet)
    ir = render_context(adapted["context"], profile=profile, backend="ABSTRACT_NFT", state=state)
    try:
        ast = lower_nft_ir(ir)
    except UnsupportedNftAction as exc:
        # BC-07 (modern ACCESS_DENY) is intentionally unresolved in the
        # current profile.  Preserve the semantic classification while
        # reporting an explicit unsupported current action to the comparator.
        return {
            "schema": "OPENKILL_NEW_CONTEXT_INTENT_V1",
            "table": {"family": "inet", "name": "fw4", "owner": "FW4", "ownership": "REFERENCE_ONLY"},
            "chains": [], "sets": [], "rules": [], "attachments": [], "ast": None,
            "rendered_text": None, "context": adapted["context"],
            "classification": ir.get("classification"), "unsupported_action": str(exc),
        }
    return {
        "schema": "OPENKILL_NEW_CONTEXT_INTENT_V1",
        "table": ast["table"],
        "chains": [dict(item, name=item["physical_name"], owner="OPENKILL", ownership="OWNED") for item in ast.get("owned_chains", ())],
        "sets": [dict(item, name=item["physical_name"], owner="OPENKILL", ownership="OWNED") for item in ast.get("sets", ())],
        "rules": [dict(item, chain=item["chain"], reason=item.get("semantic_reason"), action=item.get("action_type"), order=index) for index, item in enumerate(ast.get("rules", ()))],
        "attachments": [dict(item, name=item["physical_name"], action=item.get("action_type")) for item in ast.get("attachments", ())],
        "ast": ast,
        "rendered_text": render_nft(ir),
        "context": adapted["context"],
        "classification": ir.get("classification"),
    }


def _reason_present(intent: Mapping[str, Any], reason: str) -> bool:
    if any(item.get("reason") == reason for item in intent.get("rules", ())):
        return True
    # Some production paths encode a semantic match solely as a dynamic set
    # reference.  Treat a non-empty owned set as evidence while retaining the
    # command recorder as the independent source of truth.
    sets = intent.get("sets", ())
    names = {str(item.get("name", "")) for item in sets}
    nonempty = {str(item.get("name", "")) for item in sets if item.get("elements")}
    if reason == "NODE_ENDPOINT":
        return bool(nonempty & {"openkill_node4", "openkill_node6"})
    if reason == "LOCAL_DESTINATION":
        return bool(nonempty & {"localnetwork", "localnetwork6"})
    if reason == "CHINA_POLICY":
        return bool(nonempty & {"china_ip_route", "china_ip6_route"})
    if reason == "CHINA_PASS":
        return bool(nonempty & {"china_ip_route_pass", "china_ip6_route_pass"})
    if reason == "SERVICE_PORT":
        return bool(nonempty & {"openkill_service_ports", "common_ports"})
    if reason == "FAKEIP":
        return any("198.18." in str(item.get("expression", "")) or "fd00:ffff" in str(item.get("expression", "")) for item in intent.get("rules", ()))
    if reason == "DEFAULT_POLICY":
        return any(item.get("action") in {"MARK_PROXY", "TPROXY_PROXY", "REDIRECT_PROXY"} for item in intent.get("rules", ()))
    if reason == "CONTROL_PROTOCOL":
        return any("icmp" in str(item.get("expression", "")).lower() or "dhcp" in str(item.get("expression", "")).lower() for item in intent.get("rules", ()))
    return False


def _action_for_reason(intent: Mapping[str, Any], reason: str) -> List[str]:
    return sorted(set(item.get("action") for item in intent.get("rules", ()) if item.get("reason") == reason))


_REASON_ALIASES = {
    "CUSTOM_ACCESS": "ACCESS_CONTROL",
    "ACCESS_BYPASS": "ACCESS_CONTROL",
    "USER_BYPASS": "EXPLICIT_DIRECT",
    "CHINA_DIRECT": "CHINA_POLICY",
}


def _active_chain_for_packet(packet: Mapping[str, Any]) -> str:
    """Return the logical production classifier chain for one packet.

    This is a comparison selector, not a policy resolver.  The family and
    direction are already facts in the fixture packet; precedence remains in
    the current semantic oracle and the captured rule order.
    """

    family = str(packet.get("family", "")).upper()
    direction = str(packet.get("direction", "")).upper()
    if family not in {"IPV4", "IPV6"} or direction not in {"LAN_INGRESS", "ROUTER_OUTPUT", "TUN_INGRESS"}:
        return ""
    suffix = "" if family == "IPV4" else "_v6"
    return ("openkill_mangle_output" if direction == "ROUTER_OUTPUT" else "openkill_mangle") + suffix


def _reason_positions(intent: Mapping[str, Any], chain: str) -> Dict[str, int]:
    """Return first final-rule position for each semantic reason."""

    positions: Dict[str, int] = {}
    for rule in intent.get("rules", ()):
        if chain and rule.get("chain") != chain:
            continue
        reason = rule.get("reason") or rule.get("semantic_reason")
        if not reason:
            continue
        reason = _REASON_ALIASES.get(str(reason), str(reason))
        try:
            order = int(rule.get("order", 0))
        except (TypeError, ValueError):
            continue
        positions.setdefault(reason, order)
    return positions


def compare_intent_dimensions(
    packet: Mapping[str, Any],
    intent_case: Mapping[str, Any],
    old_intent: Mapping[str, Any],
    new_intent: Mapping[str, Any],
) -> Dict[str, Any]:
    """Compare observable intent dimensions without reimplementing policy.

    The current fixture supplies the candidate reasons for overlap cases.  We
    only compare their relative final rule order when both sides expose the
    same reason.  This avoids treating a state-level static rule or an
    unrelated family rule as a packet match while still catching a real
    precedence inversion (for example the production node insertion before a
    custom access rule).
    """

    chain = _active_chain_for_packet(packet)
    old_positions = _reason_positions(old_intent, chain)
    new_positions = _reason_positions(new_intent, chain)
    expected = intent_case.get("independent_expected_current", {})
    classifier = expected.get("classifier", {}) or {}
    expected_reason = _REASON_ALIASES.get(str(classifier.get("reason")), classifier.get("reason"))
    candidates: List[str] = []
    for value in expected.get("expected_matches", ()):
        normalized = _REASON_ALIASES.get(str(value), str(value))
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    if expected_reason and expected_reason not in candidates:
        candidates.insert(0, expected_reason)

    shared = [reason for reason in candidates if reason in old_positions and reason in new_positions]
    old_order = sorted(shared, key=lambda reason: (old_positions[reason], reason))
    new_order = sorted(shared, key=lambda reason: (new_positions[reason], reason))
    relative_order_changed = bool(len(shared) > 1 and old_order != new_order)
    expected_old_winner = old_order[0] if old_order else None
    expected_new_winner = new_order[0] if new_order else None
    winner_conflict = bool(
        expected.get("result") == "MATCH"
        and len(shared) > 1
        and expected_reason
        and (expected_old_winner != expected_reason or expected_new_winner != expected_reason)
    )
    return {
        "active_chain": chain,
        "candidate_reasons": candidates,
        "shared_reasons": shared,
        "old_positions": {reason: old_positions[reason] for reason in shared},
        "new_positions": {reason: new_positions[reason] for reason in shared},
        "old_order": old_order,
        "new_order": new_order,
        "expected_reason": expected_reason,
        "old_selected_reason": expected_old_winner,
        "new_selected_reason": expected_new_winner,
        "relative_order_changed": relative_order_changed,
        "winner_conflict": winner_conflict,
    }


def compare_current_case(
    state: Mapping[str, Any],
    packet: Mapping[str, Any],
    intent_case: Mapping[str, Any],
    old_intent: Mapping[str, Any],
    new_intent: Mapping[str, Any],
    new_context_intent: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Compare one current-profile packet against independent old intent."""

    expected = intent_case["independent_expected_current"]
    result = shadow_compare(state, packet, intent_case)
    if result.get("mismatch"):
        return {
            "id": intent_case["id"],
            "classification": "SEMANTIC_MISMATCH",
            "mismatch": {"type": "SEMANTIC_SPEC_DEFECT", "detail": result["mismatch"]},
            "old": expected.get("classifier"),
            "new": result.get("classification"),
        }
    classifier = expected.get("classifier") or {}
    expected_result = expected.get("result")
    reason = classifier.get("reason")
    known_gap = expected.get("known_gap")
    old_has = bool(reason and _reason_present(old_intent, reason))
    new_has = bool(reason and _reason_present(new_context_intent or new_intent, reason))
    # A current gap is an explicit production fact, not an error in the old
    # command recorder.  Likewise owner-disabled states intentionally have no
    # OpenKill-owned syntax.
    if (new_context_intent or {}).get("unsupported_action"):
        classification = "UNSUPPORTED_CURRENT_CASE"
    elif str(state.get("run_mode", "")).upper() == "REDIRECT":
        # The current abstract renderer deliberately has no approved
        # redirect-policy lowering for this fixture path.  Keep the scenario
        # visible without treating it as a silent direct/mark fallback.
        classification = "UNSUPPORTED_CURRENT_CASE"
    elif expected_result in {"EXPECTED_CURRENT_GAP", "INVALID_STATE"} or classifier.get("decision") == "NOT_OWNED":
        classification = "KNOWN_CURRENT_GAP" if expected_result == "EXPECTED_CURRENT_GAP" else "SEMANTIC_EQUIVALENT_STRUCTURAL_DIFF"
    elif not old_has:
        classification = "OLD_NORMALIZER_DEFECT"
    elif not new_has and reason not in {"TUN_INGRESS"}:
        classification = "NEW_RENDERER_DEFECT"
    else:
        classification = "EXACT_STRUCTURAL_MATCH"
    mismatch = None
    actual_classifier = result.get("classification") or {}
    # ``shadow_compare`` includes diagnostic trace fields; the independent
    # current oracle intentionally contains only the contract's three core
    # fields.  Compare those fields only so trace enrichment cannot look like
    # a policy mismatch.
    core_fields = ("status", "reason", "decision")
    actual_core = {key: actual_classifier.get(key) for key in core_fields}
    expected_core = {key: classifier.get(key) for key in core_fields}
    if classifier and actual_classifier and actual_core != expected_core:
        classification = "SEMANTIC_MISMATCH"
        mismatch = {"type": "SEMANTIC_SPEC_DEFECT", "old": expected_core, "new": actual_core}
    dimensions = compare_intent_dimensions(packet, intent_case, old_intent, new_context_intent or new_intent)
    if dimensions.get("winner_conflict") or dimensions.get("relative_order_changed"):
        # The captured production order is authoritative evidence for this
        # comparison.  Keep the mismatch visible; do not update the current
        # fixture or silently reinterpret it as a target behavior change.
        classification = "SEMANTIC_MISMATCH"
        mismatch = {
            "type": "SEMANTIC_SPEC_DEFECT",
            "dimension": "rule_order",
            "likely_root_cause": "PRODUCTION_BUG_CANDIDATE",
            "behavior_change_candidate": "BC-02" if {"NODE_ENDPOINT", "ACCESS_CONTROL"}.issubset(set(dimensions.get("shared_reasons", ()))) else None,
            "detail": dimensions,
        }
    return {
        "id": intent_case["id"],
        "classification": classification,
        "mismatch": mismatch,
        "expected_result": expected_result,
        "known_gap": known_gap,
        "expected": classifier,
        "old_reason_present": old_has,
        "new_reason_present": new_has,
        "old_actions": _action_for_reason(old_intent, reason) if reason else [],
        "new_actions": _action_for_reason(new_context_intent or new_intent, reason) if reason else [],
        "old_rule_count": len(old_intent.get("rules", ())),
        "new_rule_count": len(new_intent.get("rules", ())),
        "dimensions": dimensions,
    }


def dns_scope_signature(intent: Mapping[str, Any]) -> Dict[str, Any]:
    """Return physical scope evidence for LAN and router DNS paths."""

    rules = intent.get("rules", ())
    dns_rules = [item for item in rules if item.get("reason") == "DNS" or ("dport 53" in str(item.get("expression", "")).lower())]
    return {
        "lan": sorted({item.get("chain") for item in dns_rules if item.get("chain") in {"dstnat", "openkill_dns_redirect", "openkill_dns_hijack"}}),
        "router": sorted({item.get("chain") for item in dns_rules if item.get("chain") in {"nat_output", "openkill_output", "openkill_dns_redirect"}}),
        "rules": dns_rules,
    }


def _dns_family_rules(intent: Mapping[str, Any], family: str) -> List[Dict[str, Any]]:
    proto = "ipv4" if family == "IPv4" else "ipv6"
    tokens = ("meta nfproto {{{}}}".format(proto), "meta nfproto {}".format(proto))
    return [
        item
        for item in intent.get("rules", ())
        if (item.get("reason") == "DNS" or item.get("semantic_reason") == "DNS")
        and (any(token in str(item.get("expression", item.get("match_expression", ""))).lower() for token in tokens) or family == "ALL")
    ]


def dns_scope_audit(
    states: Sequence[Mapping[str, Any]],
    intent_fixture: Mapping[str, Any],
    *,
    root: Optional[pathlib.Path] = None,
) -> Dict[str, Any]:
    """Compare LAN and router DNS paths in both old and new intent models."""

    state_by_id = {normalize_state(state)["id"]: state for state in states}
    cases = {
        "LAN_V4": "SHADOW-053-v4_dns_lan",
        "ROUTER_V4": "SHADOW-054-v4_dns_router_output",
        "LAN_V6": "SHADOW-061-v6_dns_lan",
        "ROUTER_V6": "SHADOW-062-v6_dns_router_output",
    }
    records: Dict[str, Any] = {}
    for label, case_id in cases.items():
        case = next(item for item in intent_fixture["cases"] if item["id"] == case_id)
        state = state_by_id[case["state_id"]]
        harness = run_production_harness(state, packet=case["packet"], root=root)
        old = parse_nft_command_records(harness["command_records"], file_records=harness.get("file_records"))
        new = normalize_new_context_intent(state, case["packet"])
        family = case["packet"]["family"]
        old_rules = _dns_family_rules(old, family)
        new_rules = _dns_family_rules(new, family)
        records[label] = {
            "case_id": case_id,
            "family": family,
            "direction": case["packet"]["direction"],
            "old": {
                "chains": sorted({item.get("chain") for item in old_rules}),
                "actions": sorted({item.get("action") for item in old_rules}),
                "expressions": [item.get("expression") for item in old_rules],
                "function_sha256": harness.get("function_sha256"),
            },
            "new": {
                "chains": sorted({item.get("chain") for item in new_rules}),
                "actions": sorted({item.get("action") for item in new_rules}),
                "expressions": [item.get("expression") for item in new_rules],
                "logical_ids": [item.get("logical_id") for item in new_rules],
            },
        }
    lan4 = records["LAN_V4"]["new"]
    router4 = records["ROUTER_V4"]["new"]
    lan6 = records["LAN_V6"]["new"]
    router6 = records["ROUTER_V6"]["new"]
    distinct_new = (
        lan4["chains"] != router4["chains"]
        or lan4["logical_ids"] != router4["logical_ids"]
    ) and (
        lan6["chains"] != router6["chains"]
        or lan6["logical_ids"] != router6["logical_ids"]
    )
    return {
        "records": records,
        "dns_scope_distinctness": "PASS" if distinct_new else "FAIL",
        "old_lan_physical_path": records["LAN_V4"]["old"]["chains"] + records["LAN_V6"]["old"]["chains"],
        "old_router_physical_path": records["ROUTER_V4"]["old"]["chains"] + records["ROUTER_V6"]["old"]["chains"],
        "new_lan_physical_path": lan4["chains"] + lan6["chains"],
        "new_router_physical_path": router4["chains"] + router6["chains"],
    }


def coverage_summary(scenarios: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    """Return deterministic 3C scenario/category coverage counts."""

    summary: Dict[str, int] = {"total": len(scenarios)}
    for scenario in scenarios:
        category = str(scenario.get("category", "OTHER"))
        summary[category] = summary.get(category, 0) + 1
        packet = scenario.get("packet", {})
        family = packet.get("family")
        if family:
            summary[family] = summary.get(family, 0) + 1
        for tag in scenario.get("coverage", ()):
            summary[str(tag)] = summary.get(str(tag), 0) + 1
    return summary


def build_production_scenarios(
    states: Sequence[Mapping[str, Any]],
    intent_fixture: Mapping[str, Any],
    *,
    limit: int = 64,
) -> List[Dict[str, Any]]:
    """Build a broad but bounded scenario list linked to existing fixtures."""

    state_by_id = {normalize_state(state)["id"]: state for state in states}
    cases = list(intent_fixture.get("cases", ()))
    # Prefer all overlap/DNS/TUN/TProxy/owner cases, then fill with the
    # remaining current corpus in fixture order.  The linkage keeps this
    # phase grounded in already-reviewed semantic expectations.
    priority = {"OVERLAP": 0, "DNS": 1, "OWNER": 2, "IPv6_CONTROL": 3, "NODE": 4, "TUN": 5, "ACCESS": 6, "CHINA": 7, "FAKEIP": 8}
    ordered = sorted(cases, key=lambda case: (priority.get(case.get("category"), 20), case["id"]))
    selected: List[Dict[str, Any]] = []
    # Keep the primary production corpus bounded and add explicit mode/family
    # probes below.  The base fixture has no REDIRECT/TPROXY packet cases;
    # those probes are required to exercise the backend combinations without
    # changing the reviewed current-intent fixture.
    base_limit = min(limit, 64)
    for case in ordered:
        state = state_by_id.get(case.get("state_id"))
        if state is None:
            continue
        selected.append(
            {
                "id": "P3C-" + case["id"],
                "case_id": case["id"],
                "state_id": case["state_id"],
                "state": state,
                "packet": case["packet"],
                "category": case.get("category", "OTHER"),
                "coverage": list(case.get("coverage", ())),
                "production_reference": case.get("production_reference"),
            }
        )
        if len(selected) >= base_limit:
            break
    state_by_id = {normalize_state(state)["id"]: state for state in states}

    def clone_case(source_id: str, label: str, *, state_override: Optional[Mapping[str, Any]] = None, category: Optional[str] = None) -> Optional[Dict[str, Any]]:
        source = next((item for item in cases if item["id"] == source_id), None)
        if source is None:
            return None
        state = state_override or state_by_id.get(source.get("state_id"))
        if state is None:
            return None
        cloned = copy.deepcopy(source)
        cloned["id"] = "P3C-SYN-{}-{:03d}-{}".format(label, len(extras) + 1, source_id.replace("SHADOW-", ""))
        cloned["packet"]["id"] = cloned["id"] + "-PACKET"
        if category:
            cloned["category"] = category
        return {
            "id": cloned["id"],
            "case_id": cloned["id"],
            "state_id": normalize_state(state)["id"],
            "state": state,
            "packet": cloned["packet"],
            "category": cloned.get("category", "OTHER"),
            "coverage": list(cloned.get("coverage", ())),
            "production_reference": cloned.get("production_reference"),
            "intent_case": cloned,
        }

    extras: List[Dict[str, Any]] = []
    for source_id in (
        "SHADOW-001-v4_loopback", "SHADOW-003-v4_private", "SHADOW-005-v4_link_local", "SHADOW-007-v4_multicast",
        "SHADOW-009-v4_lan_prefix", "SHADOW-011-v4_wan_host", "SHADOW-013-v4_delegated_prefix", "SHADOW-015-v6_ula",
    ):
        item = clone_case(source_id, "LOCAL")
        if item: extras.append(item)
    for source_id in ("SHADOW-030-v4_tun_ingress", "SHADOW-034-v6_tun_ingress") * 4:
        item = clone_case(source_id, "TUN", category="TUN")
        if item: extras.append(item)
    dual_state = next((state for state in states if normalize_state(state)["id"] == "STATE-03-DUAL-STACK"), None)
    if dual_state is not None:
        for index, family in enumerate(("IPv4", "IPv6", "IPv4", "IPv6", "IPv4", "IPv6")):
            packet = {
                "schema": "OPENKILL_SHADOW_PACKET_V1", "id": "P3C-DUAL-{:02d}".format(index + 1),
                "family": family, "direction": "LAN_INGRESS", "protocol": "TCP",
                "src": "192.0.2.30" if family == "IPv4" else "2001:db8:230::30",
                "dst": "203.0.113.230" if family == "IPv4" else "2001:db8:230::230",
                "source_kind": "LAN", "service": "OTHER", "connection": "UNKNOWN", "self_process": False,
                "src_port": 40300, "dst_port": 443,
            }
            case_id = "P3C-DUAL-{:02d}".format(index + 1)
            extras.append({
                "id": case_id, "case_id": case_id, "state_id": "STATE-03-DUAL-STACK", "state": dual_state,
                "packet": packet, "category": "DUAL", "coverage": ["DUAL", "LAN_INGRESS"],
                "production_reference": "set_firewall:dual-stack current branch",
                "intent_case": {"id": case_id, "packet": packet, "independent_expected_current": {"result": "MATCH", "expected_matches": [], "confidence": "MEDIUM", "classifier": {"status": "VALID", "reason": "DEFAULT_POLICY", "decision": "PROXY"}}},
            })
    # Explicit TPROXY probes use a state fixture that is already part of the
    # Phase 2C contract.  Their independent expected result is the reviewed
    # DEFAULT_POLICY/PROXY current outcome.
    tproxy_state = next((state for state in states if normalize_state(state)["id"] == "STATE-12-TPROXY"), None)
    if tproxy_state is not None:
        for index, (family, protocol, direction) in enumerate(
            [("IPv4", "TCP", "LAN_INGRESS"), ("IPv4", "UDP", "LAN_INGRESS"),
             ("IPv6", "TCP", "LAN_INGRESS"), ("IPv6", "UDP", "LAN_INGRESS"),
             ("IPv4", "TCP", "ROUTER_OUTPUT"), ("IPv4", "UDP", "ROUTER_OUTPUT"),
             ("IPv6", "TCP", "ROUTER_OUTPUT"), ("IPv6", "UDP", "ROUTER_OUTPUT")]
        ):
            packet = {
                "schema": "OPENKILL_SHADOW_PACKET_V1", "id": "P3C-TPROXY-{:02d}".format(index + 1),
                "family": family, "direction": direction, "protocol": protocol,
                "src": "192.0.2.10" if family == "IPv4" else "2001:db8:200::10",
                "dst": "203.0.113.200" if family == "IPv4" else "2001:db8:200::200",
                "source_kind": "LAN" if direction == "LAN_INGRESS" else "ROUTER",
                "service": "OTHER", "connection": "UNKNOWN", "self_process": False,
                "src_port": 40000, "dst_port": 443,
            }
            extras.append({
                "id": "P3C-TPROXY-{:02d}".format(index + 1), "case_id": "P3C-TPROXY-{:02d}".format(index + 1),
                "state_id": "STATE-12-TPROXY", "state": tproxy_state, "packet": packet,
                "category": "TPROXY", "coverage": ["TPROXY", direction],
                "production_reference": "set_firewall:TPROXY current branch",
                "intent_case": {
                    "id": "P3C-TPROXY-{:02d}".format(index + 1), "packet": packet,
                    "independent_expected_current": {"result": "MATCH", "expected_matches": [], "confidence": "MEDIUM", "classifier": {"status": "VALID", "reason": "DEFAULT_POLICY", "decision": "PROXY"}},
                },
            })
    redirect_state = copy.deepcopy(tproxy_state) if tproxy_state is not None else None
    if redirect_state is not None:
        redirect_state["id"] = "STATE-P3C-REDIRECT"
        redirect_state["run_mode"] = "REDIRECT"
        for index, (family, direction) in enumerate((("IPv4", "LAN_INGRESS"), ("IPv4", "ROUTER_OUTPUT"), ("IPv6", "LAN_INGRESS"), ("IPv6", "ROUTER_OUTPUT"))):
            packet = {
                "schema": "OPENKILL_SHADOW_PACKET_V1", "id": "P3C-REDIRECT-{:02d}".format(index + 1),
                "family": family, "direction": direction, "protocol": "TCP",
                "src": "192.0.2.20" if family == "IPv4" else "2001:db8:220::20",
                "dst": "203.0.113.220" if family == "IPv4" else "2001:db8:220::220",
                "source_kind": "LAN" if direction == "LAN_INGRESS" else "ROUTER",
                "service": "OTHER", "connection": "UNKNOWN", "self_process": False,
                "src_port": 40020, "dst_port": 443,
            }
            extras.append({
                "id": "P3C-REDIRECT-{:02d}".format(index + 1), "case_id": "P3C-REDIRECT-{:02d}".format(index + 1),
                "state_id": redirect_state["id"], "state": redirect_state, "packet": packet,
                "category": "REDIRECT", "coverage": ["REDIRECT", direction],
                "production_reference": "set_firewall:REDIRECT current branch",
                "intent_case": {"id": "P3C-REDIRECT-{:02d}".format(index + 1), "packet": packet, "independent_expected_current": {"result": "MATCH", "expected_matches": [], "confidence": "LOW", "classifier": {"status": "VALID", "reason": "DEFAULT_POLICY", "decision": "PROXY"}}},
            })
    # Duplicates make the category coverage explicit while still sharing the
    # same source-audited production state and independent expected oracle.
    for source_id in ("SHADOW-053-v4_dns_lan", "SHADOW-054-v4_dns_router_output"):
        item = clone_case(source_id, "DNS", category="DNS")
        if item: extras.append(item)
    for source_id in ("SHADOW-031-v4_node_literal", "SHADOW-035-v6_node_literal", "SHADOW-032-v4_node_domain", "SHADOW-036-v6_node_domain"):
        item = clone_case(source_id, "NODE", category="NODE")
        if item: extras.append(item)
    for source_id in ("SHADOW-043-v4_china_mainland", "SHADOW-046-v6_china_mainland", "SHADOW-044-v4_china_pass", "SHADOW-047-v6_china_pass", "SHADOW-045-v4_china_overseas", "SHADOW-048-v6_china_overseas", "SHADOW-043-v4_china_mainland", "SHADOW-046-v6_china_mainland"):
        item = clone_case(source_id, "CHINA", category="CHINA")
        if item: extras.append(item)
    for source_id in ("SHADOW-037-v4_access_bypass", "SHADOW-038-v4_custom_access_deny", "SHADOW-040-v6_access_bypass", "SHADOW-041-v6_custom_access_deny", "SHADOW-037-v4_access_bypass", "SHADOW-038-v4_custom_access_deny", "SHADOW-040-v6_access_bypass", "SHADOW-041-v6_custom_access_deny"):
        item = clone_case(source_id, "ACCESS", category="ACCESS")
        if item: extras.append(item)
    selected.extend(extras[: max(0, limit - len(selected))])
    return selected


def run_shadow_comparison(
    states: Sequence[Mapping[str, Any]],
    intent_fixture: Mapping[str, Any],
    *,
    root: Optional[pathlib.Path] = None,
    scenario_limit: int = 120,
) -> Dict[str, Any]:
    """Run the local 3C comparison and return a JSON-safe report object."""

    validated_intent = validate_intent_fixture(intent_fixture)
    scenarios = build_production_scenarios(states, validated_intent, limit=scenario_limit)
    by_key: Dict[str, Dict[str, Any]] = {}
    old_by_state: Dict[str, Dict[str, Any]] = {}
    node_by_state: Dict[str, Dict[str, Any]] = {}
    root_path = _repo_root(root)
    state_by_id = {normalize_state(state)["id"]: state for state in states}
    for scenario in scenarios:
        state = scenario["state"]
        normalized = normalize_state(state)
        # Cache only identical normalized production states.  Policy and set
        # contents are part of the input; omitting them would accidentally
        # reuse (for example) a mainland-China intent for an overseas state.
        key = json.dumps(
            {"state": normalized, "packet_family": scenario["packet"].get("family")},
            sort_keys=True,
            separators=(",", ":"),
            default=list,
        )
        if key not in old_by_state:
            if normalized["owner"] in {"MIHOMO", "DISABLED", "UNKNOWN"}:
                old_by_state[key] = {"schema": "OPENKILL_OLD_NORMALIZED_INTENT_V1", "chains": [], "sets": [], "rules": [], "attachments": [], "owner": normalized["owner"], "harness": {"returncode": 0, "command_records": [], "unknown_commands": []}}
            else:
                harness = run_production_harness(state, function="set_firewall", packet=scenario["packet"], root=root_path)
                old_by_state[key] = parse_nft_command_records(
                    harness["command_records"], file_records=harness.get("file_records")
                )
                old_by_state[key]["harness"] = harness
        old_intent = old_by_state[key]
        state_id = normalized["id"]
        if state_id not in node_by_state and (normalized.get("node4") or normalized.get("node6")) and normalized["owner"] == "OPENKILL":
            node_harness = run_production_harness(
                state, function="apply_node_endpoint_sets", packet=scenario["packet"], root=root_path
            )
            node_intent = parse_nft_command_records(
                node_harness["command_records"], file_records=node_harness.get("file_records")
            )
            node_by_state[state_id] = {"harness": node_harness, "intent": node_intent}
            # Merge endpoint elements/rules into the old normalized state.
            old_intent = old_by_state[key]
            old_intent["sets"] = sorted(old_intent.get("sets", []) + node_intent.get("sets", []), key=lambda item: item.get("name", ""))
            old_intent["rules"] = old_intent.get("rules", []) + node_intent.get("rules", [])
        new_intent = normalize_new_renderer_intent(state)
        new_context_intent = normalize_new_context_intent(state, scenario["packet"])
        by_key[scenario["case_id"]] = {"old": old_intent, "new": new_intent, "new_context": new_context_intent}
    results: List[Dict[str, Any]] = []
    for scenario in scenarios:
        case = scenario.get("intent_case") or next(
            item for item in validated_intent["cases"] if item["id"] == scenario["case_id"]
        )
        pair = by_key[scenario["case_id"]]
        results.append(
            compare_current_case(
                scenario["state"], scenario["packet"], case, pair["old"], pair["new"], pair.get("new_context")
            )
        )
    classes = {name: sum(1 for item in results if item.get("classification") == name) for name in (
        "EXACT_STRUCTURAL_MATCH", "SEMANTIC_EQUIVALENT_STRUCTURAL_DIFF", "KNOWN_CURRENT_GAP",
        "UNSUPPORTED_CURRENT_CASE", "SEMANTIC_MISMATCH", "UNKNOWN", "OLD_HARNESS_DEFECT", "OLD_NORMALIZER_DEFECT", "NEW_RENDERER_DEFECT",
    )}
    return {
        "schema": PHASE_3C_SCHEMA,
        "profile": CURRENT_PROFILE,
        "scenarios": scenarios,
        "results": results,
        "coverage": coverage_summary(scenarios),
        "comparison_classes": classes,
        "scenario_count": len(scenarios),
        "old_intents": old_by_state,
        "node_harnesses": node_by_state,
        "function_hashes": production_function_hashes(root_path),
        "unknown_mismatch_count": sum(1 for item in results if item.get("classification") == "UNKNOWN"),
        "semantic_mismatch_count": sum(1 for item in results if item.get("classification") == "SEMANTIC_MISMATCH"),
    }


__all__ = [
    "COMMAND_ALLOWLIST",
    "CURRENT_PROFILE",
    "FUNCTION_SOURCES",
    "MISMATCH_CLASSES",
    "PHASE_3C_SCHEMA",
    "ProductionShadowError",
    "build_production_scenarios",
    "coverage_summary",
    "compare_current_case",
    "dns_scope_signature",
    "extract_shell_function",
    "normalize_new_renderer_intent",
    "normalize_new_context_intent",
    "parse_nft_command_records",
    "production_function_hashes",
    "dns_scope_audit",
    "run_production_harness",
    "run_shadow_comparison",
]
