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
from openkill_shadow_semantic_model import (
    COMPONENTS as SEMANTIC_COMPONENTS,
    DNS_FIELDS,
    OWNERSHIP_CLASSES,
    SEMANTIC_MODEL_SCHEMA,
    SemanticModelError,
    build_dns_fields_from_intent,
    build_dns_semantic_intent,
    build_semantic_projection,
    classify_object_ownership,
    compare_dns_semantics,
    compare_semantic_intents,
    semantic_hash,
)


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


def compare_current_semantic_intents(
    actual: Mapping[str, Any],
    desired: Mapping[str, Any],
    *,
    mode: str = "TUN",
    formal_inventory: Any = None,
    dns_actual: Optional[Mapping[str, Any]] = None,
    dns_desired: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the D2B ownership-aware CURRENT semantic comparison.

    This thin development-only adapter keeps the production-shadow module's
    public entry point stable while the model itself remains isolated from
    the device coordinator, parser, renderer, and writer paths.
    """

    return compare_semantic_intents(
        actual,
        desired,
        mode=mode,
        formal_inventory=formal_inventory,
        dns_actual=dns_actual,
        dns_desired=dns_desired,
    )


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
    # ``normalize_state`` owns the development execution extension and
    # supplies the same listener values that the production fixture models.
    # Keep the shell variables scalar: the harness must never interpolate a
    # Python mapping into Bash.
    dns_mode = str(normalized.get("dns_mode", default_dns_mode))
    proxy_ports = normalized.get("proxy_ports", {})
    proxy_port_value = int(proxy_ports.get("redirect", 7892))
    tproxy_port_value = int(proxy_ports.get("tproxy", 7895))
    dns_port_value = int(proxy_ports.get("dns", 7874))
    # ``dns_port`` is Mihomo's listener/upstream.  In the stable mode-1
    # production path set_firewall discovers dnsmasq's LAN-facing listener;
    # the checked-in OpenWrt configuration leaves that listener at its
    # default :53.  Model that independent source in the record-only harness
    # instead of accidentally feeding the Mihomo port into DNSPORT.
    dnsmasq_listen_port = 53
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
        "proxy_port": proxy_port_value,
        "tproxy_port": tproxy_port_value,
        "dns_port": dns_port_value,
        "DNSPORT": dnsmasq_listen_port,
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
        # Model only the chain-existence queries needed by the extracted
        # production body.  An unknown chain fails closed, while add-chain
        # intent registers the new name for subsequent list queries.  This
        # prevents the standalone node updater from inventing rules for
        # chains that the preceding firewall setup did not create.
        "KNOWN_CHAINS='dstnat mangle_prerouting mangle_output output srcnat input forward'",
        "chain_known(){ local _needle=\"$1\" _item; for _item in $KNOWN_CHAINS; do [ \"$_item\" = \"$_needle\" ] && return 0; done; return 1; }",
        "nft(){ local _cmd=\"$*\" _chain; case \"$_cmd\" in list\\ chain\\ inet\\ fw4\\ *) _chain=\"${_cmd#list chain inet fw4 }\"; _chain=\"${_chain%% *}\"; chain_known \"$_chain\"; return $?;; list\\ sets*|list\\ table*) return 1;; add\\ chain\\ inet\\ fw4\\ *) _chain=\"${_cmd#add chain inet fw4 }\"; _chain=\"${_chain%% *}\"; chain_known \"$_chain\" || KNOWN_CHAINS=\"$KNOWN_CHAINS $_chain\"; record nft \"$@\"; return 0;; esac; record nft \"$@\"; return 0; }",
        "iptables(){ record iptables \"$@\"; return 1; }",
        "ip6tables(){ record ip6tables \"$@\"; return 1; }",
        "ipset(){ record ipset \"$@\"; return 0; }",
        # The production writer resolves one stable dnsmasq section before it
        # reads the listener port.  Keep the legacy anonymous selector in the
        # harness as a compatibility fixture, but make both paths return the
        # same observed port so the DNS redirect contract is exercised rather
        # than falling through to an empty synthetic value.
        "uci(){ record uci \"$@\"; case \"$*\" in *'dhcp.@dnsmasq[0].port'*|*'.port'*) printf '%s' \"$DNSPORT\";; *get*|*show*) return 1;; esac; return 0; }",
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
            "proxy_port={}; tproxy_port={}; dns_port={}; DNSPORT={}".format(
                values.get("proxy_port", 7892),
                values.get("tproxy_port", 7895),
                values.get("dns_port", 7874),
                values.get("DNSPORT", values.get("dns_port", 7874)),
            ),
            "wan_int=wan; wan6_int=wan6; wan_ints=wan; wan6_ints=wan6",
            "upnp_lease_file=\"$SANDBOX/upnp\"",
            "CONFIG_FILE=\"$SANDBOX/config.yaml\"; : > \"$CONFIG_FILE\"",
            "OPENKILL_NFT_BATCH=0",
            "UNKNOWN_COUNT=0",
        ]
    )
    for key, value in values.items():
        if key in {"dns_scope", "service_ports", "DNSPORT", "proxy_port", "tproxy_port", "dns_port"}:
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
        if function == "apply_node_endpoint_sets":
            # The standalone updater is normally called after set_firewall,
            # so seed only the family-specific chains that could already
            # exist in that same normalized fixture.  The recorder still
            # learns any chain added by the extracted body itself.
            seeded = [
                "openkill", "openkill_mangle", "openkill_output", "openkill_mangle_output",
            ]
            if int(values.get("ipv6_enable", 0) or 0) == 1:
                seeded.extend(
                    ["openkill_v6", "openkill_mangle_v6", "openkill_output_v6", "openkill_mangle_output_v6"]
                )
            script += "KNOWN_CHAINS=\"$KNOWN_CHAINS {}\"\n".format(" ".join(seeded))
        # ``set_firewall`` invokes the production node endpoint updater at
        # the end of its modern path.  Include that exact function body in
        # the sandbox so the old intent contains the same dynamic node sets
        # and endpoint-protection rules; the helper commands remain stubs.
        if use_node_impl:
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
    # A mode-2 DNS attachment contains ``jump openkill_dns_redirect``.  The
    # chain name itself includes the word "redirect", so test the terminal
    # jump before looking for an actual ``redirect to`` verdict.
    if re.search(r"\bjump\s+\S+", lower):
        return "JUMP"
    if "dport 53" in lower and re.search(r"\bredirect\s+to\b", lower):
        return "DNS_REDIRECT"
    if "tproxy" in lower:
        return "TPROXY_PROXY"
    if "redirect to" in lower:
        return "REDIRECT_PROXY"
    if "mark set 0x162" in lower or "set-xmark 0x162" in lower:
        return "MARK_PROXY"
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


def _rule_merge_key(rule: Mapping[str, Any]) -> Tuple[Any, ...]:
    """Return a command-order-independent identity for one normalized rule."""

    return (
        rule.get("chain"),
        rule.get("expression"),
        rule.get("reason"),
        rule.get("action"),
    )


def _merge_nft_intent(base: Mapping[str, Any], delta: Mapping[str, Any]) -> Dict[str, Any]:
    """Merge an independently captured node update into a final old intent.

    ``set_firewall`` already invokes ``apply_node_endpoint_sets`` on the
    normal OpenKill path.  The separate capture is retained as evidence, but
    its objects must be merged with insert semantics and deduplicated rather
    than blindly appended.  This also models a caller that applies the node
    updater after the initial firewall setup.
    """

    merged = copy.deepcopy(dict(base))
    # Sets are state snapshots in the normalized vocabulary.  Unioning
    # elements is safe for the recorder's add/flush sequence and keeps stable
    # metadata from the first capture.
    sets_by_name: Dict[str, Dict[str, Any]] = {
        str(item.get("name")): dict(item) for item in merged.get("sets", ())
    }
    for item in delta.get("sets", ()):
        name = str(item.get("name"))
        if name not in sets_by_name:
            sets_by_name[name] = dict(item)
            continue
        current = sets_by_name[name]
        current["elements"] = sorted(
            set(current.get("elements", ())) | set(item.get("elements", ())),
            key=lambda value: (str(type(value)), str(value)),
        )
    merged["sets"] = sorted(sets_by_name.values(), key=lambda item: str(item.get("name", "")))

    rules_by_chain: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
    for rule in merged.get("rules", ()):
        chain = str(rule.get("chain", ""))
        rules_by_chain.setdefault(chain, []).append(dict(rule))
    known_chains = set(rules_by_chain)
    known_chains.update(str(item.get("name")) for item in merged.get("chains", ()))
    existing_keys = {_rule_merge_key(rule) for values in rules_by_chain.values() for rule in values}
    for rule in delta.get("rules", ()):
        chain = str(rule.get("chain", ""))
        # A standalone node updater may report a family chain that the
        # preceding set_firewall fixture did not create.  It is not part of
        # the old final intent for this scenario.
        if chain not in known_chains:
            continue
        candidate = dict(rule)
        key = _rule_merge_key(candidate)
        if key in existing_keys:
            continue
        bucket = rules_by_chain.setdefault(chain, [])
        if candidate.get("operation") == "insert" and candidate.get("position") in (None, 0):
            bucket.insert(0, candidate)
        elif candidate.get("operation") == "insert":
            try:
                bucket.insert(max(0, int(candidate.get("position")) - 1), candidate)
            except (TypeError, ValueError):
                bucket.insert(0, candidate)
        else:
            bucket.append(candidate)
        existing_keys.add(key)
    normalized_rules: List[Dict[str, Any]] = []
    for chain, values in rules_by_chain.items():
        for order, rule in enumerate(values):
            normalized_rules.append({**rule, "chain": chain, "order": order})
    merged["rules"] = normalized_rules
    merged["attachments"] = [
        rule
        for rule in normalized_rules
        if rule.get("chain") in {"dstnat", "mangle_prerouting", "mangle_output", "output", "srcnat", "input", "forward", "nat_output"}
        and rule.get("action") == "JUMP"
    ]
    return merged


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
        # Attachments are part of packet intent as well as topology.  Keep a
        # normalized pseudo-rule view so DNS scope and reason-presence checks
        # observe the complete parent-chain path instead of only the owned
        # body chain.
        "rules": [
            *[
                dict(item, chain=item["chain"], reason=item.get("semantic_reason"), action=item.get("action_type"), order=index)
                for index, item in enumerate(ast.get("rules", ()))
            ],
            *[
                dict(
                    item,
                    chain=item.get("from_chain") or item.get("chain"),
                    reason=item.get("semantic_reason"),
                    action=item.get("action_type"),
                    order=0,
                )
                for item in ast.get("attachments", ())
                if item.get("semantic_reason")
            ],
        ],
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


def _expression_matches_packet(expression: str, packet: Mapping[str, Any]) -> bool:
    """Apply only explicit family/transport qualifiers from an intent rule.

    This is deliberately a narrow observation helper for the old command
    recorder and the new syntax AST.  It does not evaluate addresses, sets,
    or policy precedence; those facts are compared by the semantic fixture
    and the order dimension above.
    """

    lower = str(expression or "").lower()
    family = str(packet.get("family", "")).upper()
    protocol = str(packet.get("protocol", "")).upper()
    if family == "IPV4" and (
        re.search(r"nfproto\s*\{?\s*ipv6\b", lower)
        or "ip6 " in lower
        or "ip6 daddr" in lower
        or "ip6 nexthdr" in lower
    ):
        return False
    if family == "IPV6" and (
        re.search(r"nfproto\s*\{?\s*ipv4\b", lower)
        or re.search(r"\bip\s+(?:saddr|daddr|protocol)\b", lower)
    ):
        return False
    # A rule with an explicit TCP/UDP/ICMP qualifier must agree with the
    # synthetic packet.  Unqualified rules are retained for the packet; the
    # helper is not a classifier and never invents a default protocol.
    if protocol == "TCP":
        if re.search(r"\budp\b", lower) and not re.search(r"\btcp\b", lower):
            return False
    elif protocol == "UDP":
        if re.search(r"\btcp\b", lower) and not re.search(r"\budp\b", lower):
            return False
    elif protocol == "ICMPV6":
        if re.search(r"\b(?:tcp|udp|icmp)\b", lower) and "icmpv6" not in lower:
            return False
    elif protocol == "ICMP":
        if "icmpv6" in lower or re.search(r"\b(?:tcp|udp)\b", lower):
            return False
    return True


def _attachment_target(attachment: Mapping[str, Any]) -> Optional[str]:
    target = attachment.get("to_chain")
    if target:
        return str(target)
    expression = str(attachment.get("expression") or attachment.get("match_expression") or "")
    match = re.search(r"\bjump\s+([A-Za-z0-9_.-]+)", expression)
    return match.group(1) if match else None


def _reachable_chains(intent: Mapping[str, Any], packet: Mapping[str, Any]) -> List[str]:
    """Return final classifier chains reachable for the packet facts."""

    direction = str(packet.get("direction", "")).upper()
    source_by_direction = {
        "LAN_INGRESS": {"dstnat", "mangle_prerouting", "prerouting"},
        "ROUTER_OUTPUT": {"nat_output", "mangle_output", "output"},
        # TUN ingress is represented as a classifier-chain fact rather than
        # a base-chain attachment in the current fixtures.
        "TUN_INGRESS": {"mangle_prerouting", "mangle_output", "openkill_mangle", "openkill_mangle_v6"},
    }
    allowed_sources = source_by_direction.get(direction)
    chains: List[str] = []
    for attachment in intent.get("attachments", ()):
        source = str(attachment.get("chain") or attachment.get("from_chain") or "")
        if allowed_sources is not None and source not in allowed_sources:
            continue
        expression = attachment.get("expression") or attachment.get("match_expression")
        if not _expression_matches_packet(str(expression or ""), packet):
            continue
        target = _attachment_target(attachment)
        if target and target not in chains:
            chains.append(target)
    return chains


def _proxy_action_signature(intent: Mapping[str, Any], packet: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Observe transport-qualified proxy actions on the reachable path.

    The returned values are facts extracted from already-generated intent;
    this function does not choose a winning rule.  It exists to catch a
    production/current renderer divergence such as TCP redirect versus UDP
    TPROXY, or a different TPROXY listener port.
    """

    reachable = set(_reachable_chains(intent, packet))
    if not reachable:
        # Some fixture intents are already scoped to one classifier chain and
        # do not carry an attachment.  Keep that representation observable.
        selected = _active_chain_for_packet(packet)
        if selected:
            reachable.add(selected)
    family = str(packet.get("family", "")).upper()
    protocol = str(packet.get("protocol", "")).upper()
    result: List[Dict[str, Any]] = []
    for rule in intent.get("rules", ()):
        chain = str(rule.get("chain") or "")
        if chain not in reachable:
            continue
        action = str(rule.get("action") or rule.get("action_type") or "")
        if action not in {"MARK_PROXY", "TPROXY_PROXY", "REDIRECT_PROXY"}:
            continue
        match_expression = str(rule.get("expression") or rule.get("match_expression") or "")
        if not _expression_matches_packet(match_expression, packet):
            continue
        action_expression = str(rule.get("action_expression") or "")
        combined = (match_expression + " " + action_expression).lower()
        port: Optional[int] = None
        if action == "TPROXY_PROXY":
            # Both current production forms (127.0.0.1:7893 and :7893) and
            # the development renderer form (:12345) are accepted.
            matches = re.findall(r"\b(?:tproxy|to)\b[^\n;]*?(?::|port\s+)(\d+)\b", combined)
            if matches:
                try:
                    port = int(matches[-1])
                except ValueError:
                    port = None
        elif action == "REDIRECT_PROXY":
            match = re.search(r"\bredirect\s+to\s*:?(\d+)\b", combined)
            if match:
                port = int(match.group(1))
        mark_match = re.search(r"\b(?:meta\s+)?mark(?:\s+set)?\s+(0x[0-9a-f]+|\d+)\b", combined)
        mark = mark_match.group(1).lower() if mark_match else None
        result.append(
            {
                "chain": chain,
                "family": family,
                "protocol": protocol,
                "action": action,
                "port": port,
                "mark": mark,
                "order": rule.get("order"),
            }
        )
    # A stable, duplicate-free action fact list is sufficient for parity;
    # rule order remains the responsibility of compare_intent_dimensions.
    unique: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for item in result:
        key = (item["chain"], item["family"], item["protocol"], item["action"], item["port"], item["mark"])
        unique.setdefault(key, item)
    return sorted(unique.values(), key=lambda item: (item["chain"], item["action"], item["port"] or 0, item["mark"] or ""))


def compare_proxy_transport(
    state: Mapping[str, Any],
    packet: Mapping[str, Any],
    old_intent: Mapping[str, Any],
    new_intent: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    """Compare transport action facts for the current TPROXY profile."""

    if str(state.get("run_mode", "")).upper() != "TPROXY":
        return None
    old_actions = _proxy_action_signature(old_intent, packet)
    new_actions = _proxy_action_signature(new_intent, packet)
    old_core = sorted({(item["action"], item["family"], item["protocol"], item["port"], item["mark"]) for item in old_actions})
    new_core = sorted({(item["action"], item["family"], item["protocol"], item["port"], item["mark"]) for item in new_actions})
    normalized = normalize_state(state)
    action_chains_old = sorted({item["chain"] for item in old_actions})
    action_chains_new = sorted({item["chain"] for item in new_actions})
    action_port_values = sorted({item["port"] for item in old_actions if item.get("port") is not None})
    new_port_values = sorted({item["port"] for item in new_actions if item.get("port") is not None})
    marks_old = sorted({item["mark"] for item in old_actions if item.get("mark")})
    marks_new = sorted({item["mark"] for item in new_actions if item.get("mark")})
    route_required = any(item["action"] in {"MARK_PROXY", "TPROXY_PROXY"} for item in old_actions)
    equivalent = action_port_values == new_port_values and old_core == new_core and action_chains_old == action_chains_new
    return {
        "family": packet.get("family"),
        "protocol": packet.get("protocol"),
        "direction": packet.get("direction"),
        "run_mode": normalized.get("run_mode"),
        "router_self_proxy": bool(normalized.get("router_self_proxy")),
        "configured_ports": dict(normalized.get("proxy_ports", {})),
        "old_reachable_chains": _reachable_chains(old_intent, packet),
        "new_reachable_chains": _reachable_chains(new_intent, packet),
        "old_action_chains": action_chains_old,
        "new_action_chains": action_chains_new,
        "old_actions": old_core,
        "new_actions": new_core,
        "old_ports": action_port_values,
        "new_ports": new_port_values,
        "old_marks": marks_old,
        "new_marks": marks_new,
        "route_required": route_required,
        "action_equivalent": old_core == new_core,
        "port_equivalent": action_port_values == new_port_values,
        "chain_equivalent": action_chains_old == action_chains_new,
        # Transport parity is stricter than matching only the verdict token:
        # the selected chain and configured listener port are part of the
        # current execution contract as well.
        "equivalent": equivalent,
    }


def audit_tproxy_router_self(
    states: Sequence[Mapping[str, Any]],
    *,
    root: Optional[pathlib.Path] = None,
) -> Dict[str, Any]:
    """Audit the TPROXY router-self gate for both families and transports.

    The primary 3C corpus keeps ``STATE-12-TPROXY`` with its checked-in
    ``router_self_proxy=false`` setting.  This bounded companion audit flips
    only that normalized fact in memory, then captures the exact production
    function and compares it with the current renderer.  It proves that the
    no-action gate is not being generalized to self-proxy-enabled output.
    """

    source_state = next(
        (state for state in states if normalize_state(state)["id"] == "STATE-12-TPROXY"),
        None,
    )
    if source_state is None:
        return {"scenarios": 0, "equivalent": 0, "mismatches": 0, "rows": []}
    variant = copy.deepcopy(dict(source_state))
    variant["router_self_proxy"] = True
    rows: List[Dict[str, Any]] = []
    combos = (("IPv4", "TCP"), ("IPv4", "UDP"), ("IPv6", "TCP"), ("IPv6", "UDP"))
    for family, protocol in combos:
        packet = {
            "schema": "OPENKILL_SHADOW_PACKET_V1",
            "id": "P3C1-TPROXY-ROUTER-{}-{}".format(family[-1], protocol),
            "family": family,
            "direction": "ROUTER_OUTPUT",
            "protocol": protocol,
            "src": "192.0.2.10" if family == "IPv4" else "2001:db8:200::10",
            "dst": "203.0.113.200" if family == "IPv4" else "2001:db8:200::200",
            "source_kind": "ROUTER",
            "service": "OTHER",
            "connection": "UNKNOWN",
            "self_process": False,
            "src_port": 40000,
            "dst_port": 443,
        }
        harness = run_production_harness(variant, packet=packet, root=root)
        old = parse_nft_command_records(
            harness.get("command_records", ()), file_records=harness.get("file_records")
        )
        new = normalize_new_context_intent(variant, packet)
        transport = compare_proxy_transport(variant, packet, old, new) or {}
        rows.append(
            {
                "family": family,
                "protocol": protocol,
                "router_self_proxy": True,
                "old_actions": transport.get("old_actions", []),
                "new_actions": transport.get("new_actions", []),
                "old_action_chains": transport.get("old_action_chains", []),
                "new_action_chains": transport.get("new_action_chains", []),
                "configured_ports": transport.get("configured_ports", {}),
                "equivalent": bool(transport.get("equivalent")),
            }
        )
    return {
        "scenarios": len(rows),
        "equivalent": sum(1 for row in rows if row["equivalent"]),
        "mismatches": sum(1 for row in rows if not row["equivalent"]),
        "rows": rows,
    }


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
    # A v6 TUN packet is an explicitly recorded current gap (BC-04): the
    # production oracle deliberately says DEFAULT_POLICY/PROXY while the
    # current renderer omits the symmetric TUN return.  Keep that as a known
    # gap instead of mislabelling the absence of a rule as a renderer defect.
    behavior_change = intent_case.get("behavior_change_candidate") or {}
    behavior_change_id = behavior_change.get("id") if isinstance(behavior_change, Mapping) else None
    packet_family = str(packet.get("family", "")).upper()
    packet_direction = str(packet.get("direction", "")).upper()
    router_self_proxy = bool(normalize_state(state).get("router_self_proxy"))
    if (new_context_intent or {}).get("unsupported_action"):
        classification = "UNSUPPORTED_CURRENT_CASE"
    elif classifier.get("decision") == "ACCESS_DENY":
        # Modern current production deliberately has no normalized deny
        # verdict (the legacy backend can reject, while the modern branch may
        # return/bypass).  Keep every BC-07 case explicit and bounded so it
        # cannot be mistaken for parity or silently lowered to DROP.
        classification = "UNSUPPORTED_CURRENT_CASE"
    elif str(state.get("run_mode", "")).upper() == "REDIRECT":
        # The current abstract renderer deliberately has no approved
        # redirect-policy lowering for this fixture path.  Keep the scenario
        # visible without treating it as a silent direct/mark fallback.
        classification = "UNSUPPORTED_CURRENT_CASE"
    elif (
        behavior_change_id == "BC-04"
        and packet_family == "IPV6"
        and packet_direction == "TUN_INGRESS"
        and classifier.get("reason") == "DEFAULT_POLICY"
    ):
        classification = "KNOWN_CURRENT_GAP"
    elif (
        expected_result in {"EXPECTED_CURRENT_GAP", "INVALID_STATE"}
        or classifier.get("decision") == "NOT_OWNED"
    ):
        classification = "KNOWN_CURRENT_GAP" if expected_result == "EXPECTED_CURRENT_GAP" else "SEMANTIC_EQUIVALENT_STRUCTURAL_DIFF"
    elif (
        not new_has
        and expected_result == "MATCH"
        and classifier.get("reason") == "DEFAULT_POLICY"
        and packet_direction == "ROUTER_OUTPUT"
        and not router_self_proxy
    ):
        # The current production contract intentionally has no router-output
        # proxy action while router_self_proxy is disabled.  Both sides still
        # classify the packet as DEFAULT_POLICY/PROXY; the old recorder may
        # expose a static default marker while the packet-scoped renderer
        # correctly emits no action.  This is a structural representation
        # difference, not a policy mismatch.
        classification = "SEMANTIC_EQUIVALENT_STRUCTURAL_DIFF"
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
    transport = compare_proxy_transport(state, packet, old_intent, new_context_intent or new_intent)
    if transport is not None and not transport.get("equivalent"):
        # Transport action type, family, protocol, mark, and listener port
        # are observable dataplane intent.  Keep this separate from policy
        # precedence so a backend mismatch cannot be hidden as a structural
        # difference or reinterpreted as a target behavior change.
        classification = "SEMANTIC_MISMATCH"
        mismatch = {
            "type": "SEMANTIC_SPEC_DEFECT",
            "dimension": "proxy_action",
            "likely_root_cause": "PRODUCTION_BUG_CANDIDATE",
            "detail": transport,
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
        "transport": transport,
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


def _dns_protocols(expression: str) -> List[str]:
    """Extract transport protocols from an old or new DNS match expression."""

    lower = str(expression or "").lower()
    values: set[str] = set()
    # Both production spellings (``meta l4proto``/``ip6 nexthdr``) and the
    # development IR spelling are intentionally accepted.  This is a narrow
    # normalizer, not a second policy resolver.
    for token in re.findall(r"\b(?:tcp|udp)\b", lower):
        values.add(token.upper())
    return sorted(values)


def _dns_port(expression: str) -> Optional[int]:
    match = re.search(r"\bredirect\s+to\s*:?(\d+)\b", str(expression or "").lower())
    if match:
        return int(match.group(1))
    return None


def _dns_jump_target(rule: Mapping[str, Any]) -> Optional[str]:
    target = rule.get("to_chain")
    if target:
        return str(target)
    expression = str(rule.get("action_expression") or rule.get("expression") or "")
    match = re.search(r"\bjump\s+([A-Za-z0-9_.-]+)", expression)
    return match.group(1) if match else None


def _dns_rule_expression(rule: Mapping[str, Any]) -> str:
    # ``expression`` is present on old normalized rules, while syntax AST
    # records use ``match_expression``.  Prefer the former only when it is a
    # non-empty string; some attachment pseudo-rules carry a null expression.
    value = rule.get("expression")
    if isinstance(value, str) and value:
        return value
    return str(rule.get("match_expression") or "")


def _dns_action_expression(rule: Mapping[str, Any]) -> str:
    value = rule.get("action_expression")
    if isinstance(value, str) and value:
        return value
    return str(rule.get("expression") or "")


def _dns_parent_rules(intent: Mapping[str, Any], family: str, parent: str) -> List[Dict[str, Any]]:
    """Return DNS rules on the packet's physical parent chain."""

    return [
        item
        for item in _dns_family_rules(intent, family)
        if str(item.get("chain") or item.get("from_chain") or "") == parent
    ]


def _dns_path_signature(intent: Mapping[str, Any], packet: Mapping[str, Any]) -> Dict[str, Any]:
    """Build a packet-path signature for DNS parity comparison.

    The old side may contain both LAN and router rules because ``set_firewall``
    creates the complete dataplane.  Selecting the packet's parent chain here
    prevents an unrelated LAN rule from making a router comparison look
    equivalent.  For a jump-based LAN mode, the body chain is followed and its
    redirect action/port is included in the signature.
    """

    family_raw = str(packet.get("family", "")).upper()
    family = "IPv4" if family_raw in {"IPV4", "4"} else "IPv6" if family_raw in {"IPV6", "6"} else family_raw
    direction = str(packet.get("direction", "")).upper()
    parent = "dstnat" if direction == "LAN_INGRESS" else "nat_output" if direction == "ROUTER_OUTPUT" else ""
    parent_rules = _dns_parent_rules(intent, family, parent) if parent else []
    parent_rule = parent_rules[0] if parent_rules else None
    if parent_rule is None:
        return {
            "family": family,
            "direction": direction,
            "parent_chain": parent or None,
            "attachment_action": None,
            "attachment_target": None,
            "body_chain": None,
            "body_action": None,
            "target_port": None,
            "protocols": [],
            "scope_gate": None,
            "local_destination": None,
            "rule_order": [],
        }

    parent_expression = _dns_rule_expression(parent_rule)
    parent_action = str(parent_rule.get("action") or parent_rule.get("action_type") or "")
    parent_target = _dns_jump_target(parent_rule) if parent_action == "JUMP" else None
    body_rule: Optional[Mapping[str, Any]] = None
    body_chain = parent_target
    body_order = 0
    if body_chain:
        body_candidates = [
            item
            for item in _dns_family_rules(intent, family)
            if str(item.get("chain") or "") == body_chain
        ]
        if body_candidates:
            body_candidates = sorted(body_candidates, key=lambda item: int(item.get("order", 0)))
            body_rule = body_candidates[0]
            # The old complete setup can contain an IPv4 rule before the
            # IPv6 rule in the shared body chain.  Compare the packet-family
            # relative order, rather than the absolute mixed-family index.
            body_order = 0

    body_expression = _dns_rule_expression(body_rule or {})
    body_action_expression = _dns_action_expression(body_rule or {})
    direct_action_expression = _dns_action_expression(parent_rule)
    action_expression = body_action_expression if body_rule else direct_action_expression
    all_expression = " ".join(part for part in (parent_expression, body_expression) if part)
    scope_gate = "SELF_PROCESS_EXCLUDED" if "skgid != 65534" in all_expression.lower() else None
    local_destination = None
    if "127.0.0.1" in all_expression:
        local_destination = "127.0.0.1"
    elif "::1" in all_expression:
        local_destination = "::1"
    return {
        "family": family,
        "direction": direction,
        "parent_chain": parent,
        "attachment_action": parent_action,
        "attachment_target": parent_target,
        "body_chain": body_chain,
        "body_action": str((body_rule or parent_rule).get("action") or (body_rule or parent_rule).get("action_type") or ""),
        "target_port": _dns_port(action_expression),
        "protocols": _dns_protocols(all_expression),
        "scope_gate": scope_gate,
        "local_destination": local_destination,
        "rule_order": [
            {
                "chain": parent,
                "order": int(parent_rule.get("order", 0)),
            },
            *([{"chain": body_chain, "order": body_order}] if body_rule else []),
        ],
    }


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
    # Add the shared mode-2 fixture as a second packet-path sample.  The
    # baseline cases above exercise the direct redirect (mode 1); mode 2
    # proves that the LAN dstnat jump and its owned body remain equivalent on
    # both families without conflating them with router nat_output.
    mode2_packets = {
        "LAN_V4_MODE2": {
            "state_id": "STATE-09-SELF-PROXY",
            "packet": {
                "schema": "OPENKILL_SHADOW_PACKET_V1", "id": "P3C1-DNS-LAN-V4-M2",
                "family": "IPv4", "direction": "LAN_INGRESS", "protocol": "UDP",
                "src": "192.0.2.9", "dst": "198.51.100.53", "source_kind": "LAN",
                "service": "DNS", "connection": "UNKNOWN", "self_process": False,
                "src_port": 40009, "dst_port": None,
            },
        },
        "ROUTER_V4_MODE2": {
            "state_id": "STATE-09-SELF-PROXY",
            "packet": {
                "schema": "OPENKILL_SHADOW_PACKET_V1", "id": "P3C1-DNS-ROUTER-V4-M2",
                "family": "IPv4", "direction": "ROUTER_OUTPUT", "protocol": "TCP",
                "src": "192.0.2.9", "dst": "127.0.0.1", "source_kind": "ROUTER",
                "service": "DNS", "connection": "UNKNOWN", "self_process": False,
                "src_port": 40009, "dst_port": None,
            },
        },
        "LAN_V6_MODE2": {
            "state_id": "STATE-09-SELF-PROXY",
            "packet": {
                "schema": "OPENKILL_SHADOW_PACKET_V1", "id": "P3C1-DNS-LAN-V6-M2",
                "family": "IPv6", "direction": "LAN_INGRESS", "protocol": "UDP",
                "src": "2001:db8:9::9", "dst": "2001:db8:100::53", "source_kind": "LAN",
                "service": "DNS", "connection": "UNKNOWN", "self_process": False,
                "src_port": 40009, "dst_port": None,
            },
        },
        "ROUTER_V6_MODE2": {
            "state_id": "STATE-09-SELF-PROXY",
            "packet": {
                "schema": "OPENKILL_SHADOW_PACKET_V1", "id": "P3C1-DNS-ROUTER-V6-M2",
                "family": "IPv6", "direction": "ROUTER_OUTPUT", "protocol": "TCP",
                "src": "2001:db8:9::9", "dst": "::1", "source_kind": "ROUTER",
                "service": "DNS", "connection": "UNKNOWN", "self_process": False,
                "src_port": 40009, "dst_port": None,
            },
        },
    }
    records: Dict[str, Any] = {}
    case_records: Dict[str, Dict[str, Any]] = {}
    for label, case_id in cases.items():
        case = next(item for item in intent_fixture["cases"] if item["id"] == case_id)
        case_records[label] = {"state": state_by_id[case["state_id"]], "packet": case["packet"], "case_id": case_id}
    for label, value in mode2_packets.items():
        state = state_by_id.get(value["state_id"])
        if state is not None:
            case_records[label] = {"state": state, "packet": value["packet"], "case_id": label}
    for label, case_info in case_records.items():
        case = case_info
        state = case["state"]
        packet = case["packet"]
        harness = run_production_harness(state, packet=packet, root=root)
        old = parse_nft_command_records(harness["command_records"], file_records=harness.get("file_records"))
        new = normalize_new_context_intent(state, packet)
        family = packet["family"]
        old_rules = _dns_family_rules(old, family)
        new_rules = _dns_family_rules(new, family)
        old_path = _dns_path_signature(old, packet)
        new_path = _dns_path_signature(new, packet)
        records[label] = {
            "case_id": case["case_id"],
            "family": family,
            "direction": packet["direction"],
            "old": {
                "chains": sorted({item.get("chain") for item in old_rules}),
                "actions": sorted({item.get("action") for item in old_rules}),
                "expressions": [item.get("expression") for item in old_rules],
                "function_sha256": harness.get("function_sha256"),
                "path_signature": old_path,
            },
            "new": {
                "chains": sorted({item.get("chain") for item in new_rules}),
                "actions": sorted({item.get("action") for item in new_rules}),
                "expressions": [_dns_rule_expression(item) for item in new_rules],
                "logical_ids": [item.get("logical_id") for item in new_rules],
                "path_signature": new_path,
            },
            "packet_action_body_equivalent": old_path == new_path,
            "hook_equivalent": old_path.get("parent_chain") == new_path.get("parent_chain"),
        }

    def _pair_distinct(lan_label: str, router_label: str) -> bool:
        lan = records.get(lan_label, {}).get("new", {}).get("path_signature", {})
        router = records.get(router_label, {}).get("new", {}).get("path_signature", {})
        return bool(lan and router and lan != router)

    distinct_new = _pair_distinct("LAN_V4", "ROUTER_V4") and _pair_distinct("LAN_V6", "ROUTER_V6")
    all_records = list(records.values())
    packet_parity = all(item.get("packet_action_body_equivalent") for item in all_records)
    hook_parity = all(item.get("hook_equivalent") for item in all_records)
    # Explicitly compare the complete path, not only a body-chain hash.  This
    # closes the Phase 3C DNS blocker where LAN and router bodies happened to
    # serialize identically despite different physical attachments.
    dns_paths = {
        "LAN": {
            family: records[label]["new"]["path_signature"]
            for family, label in (("IPv4", "LAN_V4"), ("IPv6", "LAN_V6"))
        },
        "ROUTER": {
            family: records[label]["new"]["path_signature"]
            for family, label in (("IPv4", "ROUTER_V4"), ("IPv6", "ROUTER_V6"))
        },
    }
    return {
        "records": records,
        "dns_scope_distinctness": "PASS" if distinct_new else "FAIL",
        "dns_packet_action_body_parity": "PASS" if packet_parity else "FAIL",
        "dns_current_hook_parity": "PASS" if hook_parity else "FAIL",
        "dns_paths": dns_paths,
        "old_lan_physical_path": records["LAN_V4"]["old"]["chains"] + records["LAN_V6"]["old"]["chains"],
        "old_router_physical_path": records["ROUTER_V4"]["old"]["chains"] + records["ROUTER_V6"]["old"]["chains"],
        "new_lan_physical_path": records["LAN_V4"]["new"]["chains"] + records["LAN_V6"]["new"]["chains"],
        "new_router_physical_path": records["ROUTER_V4"]["new"]["chains"] + records["ROUTER_V6"]["new"]["chains"],
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


def audit_acl_node_order(
    states: Sequence[Mapping[str, Any]],
    intent_fixture: Mapping[str, Any],
    *,
    root: Optional[pathlib.Path] = None,
) -> Dict[str, Any]:
    """Recover final NODE/ACCESS order for every family classifier chain.

    The audit intentionally runs the exact ``set_firewall`` body through the
    record-only harness for the two reviewed overlap fixtures.  It then
    reports operation text *and* final simulated indexes, so a sequence of
    ``insert ... position 0`` calls cannot be mistaken for source order.
    """

    state_by_id = {normalize_state(state)["id"]: state for state in states}
    overlap_ids = ("SHADOW-066-overlap_access_node_v4", "SHADOW-067-overlap_access_node_v6")
    chains = (
        "openkill", "openkill_mangle", "openkill_output", "openkill_mangle_output",
        "openkill_v6", "openkill_mangle_v6", "openkill_output_v6", "openkill_mangle_output_v6",
    )
    rows: List[Dict[str, Any]] = []
    evidence: Dict[str, Any] = {}
    for case_id in overlap_ids:
        case = next((item for item in intent_fixture.get("cases", ()) if item.get("id") == case_id), None)
        if not case:
            continue
        state = state_by_id.get(case.get("state_id"))
        if state is None:
            continue
        harness = run_production_harness(state, packet=case.get("packet"), root=root)
        parsed = parse_nft_command_records(harness.get("command_records", ()), file_records=harness.get("file_records"))
        evidence[case_id] = {
            "state_id": normalize_state(state)["id"],
            "function_sha256": harness.get("function_sha256"),
            "node_insert_operations": [
                line for line in harness.get("command_records", ())
                if "insert rule" in line and "node underlay" in line.lower()
            ],
            # Production currently adds ACL rules (rather than inserting
            # them), while node endpoint updates use ``insert ... position
            # 0``.  Keep both operation forms in the audit so the final
            # order is derived from the simulated chain, never from the
            # spelling of the command.
            "access_insert_operations": [
                line for line in harness.get("command_records", ())
                if ("add rule" in line or "insert rule" in line)
                and any(token in line.lower() for token in ("lan_ac_", "wan_ac_", "access"))
            ],
        }
        evidence[case_id]["access_operations"] = evidence[case_id]["access_insert_operations"]
        for chain in chains:
            chain_rules = [item for item in parsed.get("rules", ()) if item.get("chain") == chain]
            node = [item for item in chain_rules if item.get("reason") == "NODE_ENDPOINT"]
            access = [item for item in chain_rules if item.get("reason") == "ACCESS_CONTROL"]
            node_index = min((int(item.get("order", 0)) for item in node), default=None)
            access_index = min((int(item.get("order", 0)) for item in access), default=None)
            if node_index is not None and access_index is not None:
                winner = "NODE_ENDPOINT" if node_index < access_index else "ACCESS_CONTROL"
            else:
                winner = "NOT_APPLICABLE"
            rows.append(
                {
                    "case_id": case_id,
                    "chain": chain,
                    "node_insert_operation": evidence[case_id]["node_insert_operations"],
                    "access_insert_operation": evidence[case_id]["access_insert_operations"],
                    "access_operation": evidence[case_id]["access_operations"],
                    "final_node_index": node_index,
                    "final_access_index": access_index,
                    "winner": winner,
                }
            )
    both = [row for row in rows if row["winner"] != "NOT_APPLICABLE"]
    winners = {row["winner"] for row in both}
    classification = "CURRENT_SEMANTIC_BASELINE_DEFECT" if winners == {"NODE_ENDPOINT"} else (
        "CURRENT_CHAIN_SPECIFIC_BEHAVIOR" if len(winners) > 1 else "UNRESOLVED"
    )
    return {
        "chains": list(chains),
        "rows": rows,
        "evidence": evidence,
        "winners": sorted(winners),
        "classification": classification,
        "all_node_before_access": bool(both) and winners == {"NODE_ENDPOINT"},
    }


def enumerate_unsupported_current_cases(
    results: Sequence[Mapping[str, Any]],
    scenarios: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Classify every bounded current unsupported scenario.

    Unsupported is deliberately explicit.  BC-07 modern deny cases remain
    reachable production semantics with no approved modern verdict, while
    REDIRECT probes are development-only synthetic coverage (the checked-in
    production scenarios use TUN/TPROXY).  Neither category is silently
    treated as direct or proxy.
    """

    scenario_by_id = {str(item.get("id")): item for item in scenarios}
    rows: List[Dict[str, Any]] = []
    for result in results:
        if result.get("classification") != "UNSUPPORTED_CURRENT_CASE":
            continue
        scenario = scenario_by_id.get(str(result.get("id")), {})
        state = scenario.get("state", {}) if isinstance(scenario, Mapping) else {}
        expected = result.get("expected") or {}
        decision = expected.get("decision")
        if decision == "ACCESS_DENY":
            category = "BC-07_KNOWN_UNSUPPORTED"
            reachable = True
            fallback = "OLD_PRODUCTION_OR_LEGACY_BACKEND"
            reason = "Modern current ACCESS_DENY verdict is backend-dependent and not approved for central lowering."
        elif str(state.get("run_mode", "")).upper() == "REDIRECT":
            category = "FIXTURE_ONLY_NON_PRODUCTION"
            reachable = False
            fallback = "NO_PRODUCTION_HANDOFF"
            reason = "Synthetic REDIRECT probe has no checked-in production scenario baseline."
        else:
            category = "BACKEND_CAPABILITY_UNSUPPORTED"
            reachable = True
            fallback = "RETAIN_OLD_IMPLEMENTATION"
            reason = "Current backend action is not expressible by the development renderer contract."
        rows.append(
            {
                "id": result.get("id"),
                "reason": reason,
                "production_reachable": reachable,
                "classification": category,
                "future_fallback_required": fallback,
                "production_reference": scenario.get("production_reference"),
                "behavior_change_candidate": "BC-07" if decision == "ACCESS_DENY" else None,
            }
        )
    rows.sort(key=lambda item: str(item.get("id", "")))
    return rows


def enumerate_known_current_gaps(
    results: Sequence[Mapping[str, Any]],
    scenarios: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Group known current-gap scenarios by their reviewed BC identifier."""

    scenario_by_id = {str(item.get("id")): item for item in scenarios}
    groups: Dict[str, Dict[str, Any]] = {}
    for result in results:
        if result.get("classification") != "KNOWN_CURRENT_GAP":
            continue
        scenario = scenario_by_id.get(str(result.get("id")), {})
        expected = result.get("expected") or {}
        gap_id = result.get("known_gap")
        if not gap_id:
            candidate = scenario.get("behavior_change_candidate") if isinstance(scenario, Mapping) else None
            if isinstance(candidate, Mapping):
                gap_id = candidate.get("id")
        if not gap_id and str(scenario.get("packet", {}).get("family", "")).upper() == "IPV6" and str(scenario.get("packet", {}).get("direction", "")).upper() == "TUN_INGRESS":
            gap_id = "BC-04"
        gap_id = str(gap_id or "UNIDENTIFIED_CURRENT_GAP")
        group = groups.setdefault(
            gap_id,
            {
                "id": gap_id,
                "case_ids": [],
                "reasons": [],
                "current": expected,
                "production_reachable": True,
            },
        )
        group["case_ids"].append(result.get("id"))
        if expected.get("reason") not in group["reasons"]:
            group["reasons"].append(expected.get("reason"))
    for group in groups.values():
        group["case_ids"] = sorted(group["case_ids"])
        group["reasons"] = sorted(item for item in group["reasons"] if item)
    return [groups[key] for key in sorted(groups)]


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
    priority = {
        "OVERLAP": 0,
        "DNS": 1,
        "OWNER": 2,
        "IPv6_CONTROL": 3,
        # Keep the four explicit-policy current gaps in the primary corpus;
        # they are production-reachable unresolved mappings and must not be
        # lost merely because the broad scenario budget is bounded.
        "USER_DIRECT": 4,
        "USER_PROXY": 4,
        # Keep both current ACCESS_DENY oracle cases in the bounded corpus;
        # they define the explicit BC-07 unsupported boundary.
        "ACCESS": 4,
        "NODE": 5,
        "TUN": 6,
        "CHINA": 8,
        "FAKEIP": 9,
    }
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
        for index, family in enumerate(("IPv4", "IPv6", "IPv4", "IPv6", "IPv4")):
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
    for source_id in (
        "SHADOW-031-v4_node_literal", "SHADOW-035-v6_node_literal",
        "SHADOW-032-v4_node_domain", "SHADOW-036-v6_node_domain",
        # Keep a fifth node probe available when the bounded corpus is
        # rebalanced to retain all explicit ACCESS_DENY cases.
        "SHADOW-031-v4_node_literal",
    ):
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
            # Merge endpoint elements/rules into the old normalized state
            # with the same insert-at-zero semantics as the production
            # updater.  The set_firewall body already includes the updater on
            # the OpenKill path; _merge_nft_intent therefore deduplicates
            # those objects instead of double-counting them.
            old_by_state[key] = _merge_nft_intent(old_by_state[key], node_intent)
            old_intent = old_by_state[key]
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
    transport_results = [item.get("transport") for item in results if item.get("transport") is not None]
    unsupported_cases = enumerate_unsupported_current_cases(results, scenarios)
    known_current_gaps = enumerate_known_current_gaps(results, scenarios)
    acl_node_audit = audit_acl_node_order(states, validated_intent, root=root_path)
    dns_audit = dns_scope_audit(states, validated_intent, root=root_path)
    tproxy_router_self = audit_tproxy_router_self(states, root=root_path)
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
        "tproxy_parity": {
            "scenarios": len(transport_results),
            "equivalent": sum(1 for item in transport_results if item.get("equivalent")),
            "mismatches": sum(1 for item in transport_results if not item.get("equivalent")),
            "results": transport_results,
        },
        "tproxy_router_self": tproxy_router_self,
        "acl_node_audit": acl_node_audit,
        "unsupported_current_cases": unsupported_cases,
        "known_current_gaps": known_current_gaps,
        "unbounded_unsupported_current_case": any(
            item.get("production_reachable") and item.get("classification") not in {
                "BC-07_KNOWN_UNSUPPORTED", "BACKEND_CAPABILITY_UNSUPPORTED"
            }
            for item in unsupported_cases
        ),
        "dns_audit": dns_audit,
        "bc_target_leakage_count": sum(
            1 for item in results if "TARGET" in json.dumps(item, sort_keys=True, default=str)
        ),
    }


__all__ = [
    "COMMAND_ALLOWLIST",
    "SEMANTIC_COMPONENTS",
    "DNS_FIELDS",
    "OWNERSHIP_CLASSES",
    "SEMANTIC_MODEL_SCHEMA",
    "SemanticModelError",
    "build_dns_fields_from_intent",
    "build_dns_semantic_intent",
    "build_semantic_projection",
    "classify_object_ownership",
    "compare_dns_semantics",
    "compare_semantic_intents",
    "compare_current_semantic_intents",
    "semantic_hash",
    "CURRENT_PROFILE",
    "FUNCTION_SOURCES",
    "MISMATCH_CLASSES",
    "PHASE_3C_SCHEMA",
    "ProductionShadowError",
    "build_production_scenarios",
    "coverage_summary",
    "compare_current_case",
    "compare_proxy_transport",
    "audit_tproxy_router_self",
    "audit_acl_node_order",
    "enumerate_unsupported_current_cases",
    "enumerate_known_current_gaps",
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
