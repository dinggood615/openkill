#!/usr/bin/env python3
"""Source and model tests for OpenKill's start/stop UCI lifecycle contract.

This suite is deliberately local.  It reads the checked-in OpenWrt scripts,
then exercises a small in-memory model of the documented dnsmasq transition.
It never invokes UCI, init scripts, nft, a network command, or a device.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "luci-app-openkill/root/etc/init.d/openkill"
SHARE = ROOT / "luci-app-openkill/root/usr/share/openkill"
MAKEFILE = ROOT / "luci-app-openkill/Makefile"
INSTALLER = ROOT / "scripts/install-openkill.sh"


FIELD_MODEL = {
    # OpenKill fields that hold reversible dnsmasq backups or lifecycle flags.
    "redirect_dns": ("OPENKILL", "REQUIRED_TRANSIENT_RUNTIME_STATE"),
    "dnsmasq_server": ("OPENKILL", "REQUIRED_BACKUP_FOR_ROLLBACK"),
    "dnsmasq_noresolv": ("OPENKILL", "REQUIRED_BACKUP_FOR_ROLLBACK"),
    "dnsmasq_resolvfile": ("OPENKILL", "REQUIRED_BACKUP_FOR_ROLLBACK"),
    "dnsmasq_cachesize": ("OPENKILL", "REQUIRED_BACKUP_FOR_ROLLBACK"),
    "cachesize_dns": ("OPENKILL", "REQUIRED_TRANSIENT_RUNTIME_STATE"),
    "dnsmasq_filter_aaaa": ("OPENKILL", "REQUIRED_BACKUP_FOR_ROLLBACK"),
    "filter_aaaa_dns": ("OPENKILL", "REQUIRED_TRANSIENT_RUNTIME_STATE"),
    "default_resolvfile": ("OPENKILL", "REQUIRED_BACKUP_FOR_ROLLBACK"),
    "last_start_failed": ("OPENKILL", "REQUIRED_TRANSIENT_RUNTIME_STATE"),
    "compatibility_fallback": ("OPENKILL", "PERSISTENT_USER_CONFIG"),
    "compatibility_fallback_reason": ("OPENKILL", "PERSISTENT_USER_CONFIG"),
    "core_arch": ("OPENKILL", "PERSISTENT_USER_CONFIG"),
    "core_type": ("OPENKILL", "PERSISTENT_USER_CONFIG"),
    "config_path": ("OPENKILL", "PERSISTENT_USER_CONFIG"),
    # Subscription sections are user-owned and are only written by the
    # missing-config/overwrite paths, never by the target-present D2D path.
    "subscribe_info.url": ("OPENKILL", "PERSISTENT_USER_CONFIG"),
    "@subscribe_info": ("OPENKILL", "PERSISTENT_USER_CONFIG"),
    "config_age_secret": ("OPENKILL", "PERSISTENT_USER_CONFIG"),
    # A one-shot generated section is lifecycle state, not a user profile.
    "@overwrite[0]": ("OPENKILL", "REQUIRED_TRANSIENT_RUNTIME_STATE"),
    # dnsmasq values are owned by the DHCP package while OpenKill is active.
    "dhcp.@dnsmasq[0].server": ("DHCP", "EXPECTED_DNSMASQ_RUNTIME_MUTATION"),
    "dhcp.@dnsmasq[0].noresolv": ("DHCP", "EXPECTED_DNSMASQ_RUNTIME_MUTATION"),
    "dhcp.@dnsmasq[0].resolvfile": ("DHCP", "EXPECTED_DNSMASQ_RUNTIME_MUTATION"),
    "dhcp.@dnsmasq[0].localuse": ("DHCP", "EXPECTED_DNSMASQ_RUNTIME_MUTATION"),
    "dhcp.@dnsmasq[0].cachesize": ("DHCP", "EXPECTED_DNSMASQ_RUNTIME_MUTATION"),
    "dhcp.@dnsmasq[0].filter_aaaa": ("DHCP", "EXPECTED_DNSMASQ_RUNTIME_MUTATION"),
    # The include is integration metadata owned by OpenKill/firewall, not a
    # user profile option.  ucitrack is installed integration metadata.
    "firewall.openkill": ("FIREWALL", "REQUIRED_TRANSIENT_RUNTIME_STATE"),
    # Native Mihomo takeover has a documented one-way compatibility migration:
    # fw4 rejects PassWall's obsolete reload flag.  It is conditional on the
    # native owner and is not part of the normal TUN delta.
    "firewall.passwall.reload": ("FIREWALL", "PERSISTENT_USER_CONFIG"),
    "ucitrack.@openkill": ("UCITRACK", "PERSISTENT_USER_CONFIG"),
}


REVERSIBLE_OPENKILL_BACKUPS = {
    "dnsmasq_server",
    "dnsmasq_cachesize",
    "dnsmasq_filter_aaaa",
}

# These values are saved by OpenKill and are deliberately retained as
# rollback metadata.  They are needed by a later redirect transition and are
# therefore not transient fields that stop should delete.
PERSISTENT_BACKUP_METADATA = {
    "dnsmasq_noresolv",
    "dnsmasq_resolvfile",
    "default_resolvfile",
}

OPENKILL_BACKUPS = REVERSIBLE_OPENKILL_BACKUPS | PERSISTENT_BACKUP_METADATA

DHCP_RUNTIME_FIELDS = {
    "server",
    "noresolv",
    "resolvfile",
    "localuse",
    "cachesize",
    "filter_aaaa",
}


def classify_field(field):
    """Return the explicit classification, failing closed for unknown writes."""
    return FIELD_MODEL.get(field, ("UNKNOWN", "FORBIDDEN_UNEXPECTED_MUTATION"))[1]


def function_block(source, name, next_name=None):
    """Return a shell function body without depending on a shell parser."""
    start = source.index(name + "()")
    if next_name:
        end = source.index(next_name + "()", start + len(name) + 3)
        return source[start:end]
    return source[start:]


def apply_dnsmasq_model(state, dns_port="7874", ipv6_dns=True):
    """Model the documented mode-1 transition for a representative UCI map."""
    state = {"openkill": dict(state["openkill"]), "dhcp": dict(state["dhcp"])}
    state["openkill"]["dnsmasq_server"] = list(state["dhcp"].get("server", []))
    state["openkill"]["dnsmasq_noresolv"] = state["dhcp"].get("noresolv", "")
    state["openkill"]["dnsmasq_resolvfile"] = state["dhcp"].get("resolvfile", "")
    state["openkill"]["dnsmasq_cachesize"] = state["dhcp"].get("cachesize", "")
    state["openkill"]["redirect_dns"] = "1"
    state["openkill"]["cachesize_dns"] = "1"
    state["dhcp"]["server"] = [f"127.0.0.1#{dns_port}"]
    state["dhcp"].pop("resolvfile", None)
    state["dhcp"]["noresolv"] = "1"
    # The init script deliberately converges this OpenWrt option to 1.
    state["dhcp"]["localuse"] = "1"
    state["dhcp"]["cachesize"] = "0"
    if ipv6_dns:
        state["openkill"]["dnsmasq_filter_aaaa"] = state["dhcp"].get("filter_aaaa", "")
        state["openkill"]["filter_aaaa_dns"] = "1"
        state["dhcp"]["filter_aaaa"] = "0"
    return state


def revert_dnsmasq_model(running, original):
    """Model the normal stop convergence for the same representative map."""
    state = {"openkill": dict(running["openkill"]), "dhcp": dict(running["dhcp"])}
    state["dhcp"]["server"] = list(original["dhcp"].get("server", []))
    for key in ("noresolv", "resolvfile", "cachesize", "filter_aaaa"):
        if key in original["dhcp"]:
            state["dhcp"][key] = original["dhcp"][key]
        else:
            state["dhcp"].pop(key, None)
    # Formal stop semantics use the OpenWrt local-use default.
    state["dhcp"]["localuse"] = "1"
    # The source converges lifecycle markers to zero and removes the
    # reversible saved values.  Resolver backups remain as intentionally
    # persistent metadata so a later start can restore the same baseline.
    state["openkill"]["redirect_dns"] = "0"
    state["openkill"]["cachesize_dns"] = "0"
    state["openkill"]["filter_aaaa_dns"] = "0"
    for key in REVERSIBLE_OPENKILL_BACKUPS:
        state["openkill"].pop(key, None)
    return state


class UciLifecycleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.init = INIT.read_text(encoding="utf-8")
        cls.normalize = (SHARE / "openkill_config_normalize.sh").read_text(encoding="utf-8")
        cls.watchdog = (SHARE / "openkill_watchdog.sh").read_text(encoding="utf-8")
        cls.makefile = MAKEFILE.read_text(encoding="utf-8")
        cls.installer = INSTALLER.read_text(encoding="utf-8")

    def test_field_model_is_explicit_and_disjoint(self):
        allowed = {
            "REQUIRED_TRANSIENT_RUNTIME_STATE",
            "REQUIRED_BACKUP_FOR_ROLLBACK",
            "EXPECTED_DNSMASQ_RUNTIME_MUTATION",
            "PERSISTENT_USER_CONFIG",
            "FORBIDDEN_UNEXPECTED_MUTATION",
        }
        self.assertEqual(set(FIELD_MODEL), FIELD_MODEL.keys())
        self.assertTrue(all(owner and classification in allowed for owner, classification in FIELD_MODEL.values()))
        self.assertNotIn("config_path", OPENKILL_BACKUPS)
        self.assertTrue(PERSISTENT_BACKUP_METADATA.issubset(OPENKILL_BACKUPS))
        self.assertTrue(REVERSIBLE_OPENKILL_BACKUPS.isdisjoint(PERSISTENT_BACKUP_METADATA))
        self.assertTrue(OPENKILL_BACKUPS.isdisjoint({"server", "noresolv", "resolvfile"}))

    def test_unknown_uci_write_is_forbidden_until_classified(self):
        self.assertEqual(classify_field("config_path"), "PERSISTENT_USER_CONFIG")
        self.assertEqual(classify_field("dhcp.@dnsmasq[0].server"), "EXPECTED_DNSMASQ_RUNTIME_MUTATION")
        self.assertEqual(classify_field("unreviewed_option"), "FORBIDDEN_UNEXPECTED_MUTATION")

    def test_change_dnsmasq_declares_exact_runtime_delta(self):
        block = function_block(self.init, "change_dnsmasq", "revert_dnsmasq")
        for marker in (
            "uci -q set openkill.config.dnsmasq_noresolv=",
            "uci -q set openkill.config.dnsmasq_resolvfile=",
            "uci -q set openkill.config.dnsmasq_cachesize=",
            "uci -q set openkill.config.dnsmasq_filter_aaaa=",
            "uci -q set openkill.config.redirect_dns=1",
            "uci -q set openkill.config.cachesize_dns=1",
            "uci -q set openkill.config.filter_aaaa_dns=1",
            "uci -q del dhcp.@dnsmasq[-1].server",
            'uci -q add_list dhcp.@dnsmasq[0].server=127.0.0.1#"$dns_port"',
            "uci -q delete dhcp.@dnsmasq[0].resolvfile",
            "uci -q set dhcp.@dnsmasq[0].noresolv=1",
            "uci -q set dhcp.@dnsmasq[0].localuse=1",
            "uci -q set dhcp.@dnsmasq[0].cachesize=0",
            "uci -q set dhcp.@dnsmasq[0].filter_aaaa=0",
            "uci -q commit openkill",
            "uci -q commit dhcp",
            "/etc/init.d/dnsmasq restart",
        ):
            self.assertIn(marker, block, marker)

        for marker in (
            "uci -q set openkill.config.redirect_dns=0",
            "uci -q set openkill.config.cachesize_dns=0",
            "uci -q set openkill.config.filter_aaaa_dns=0",
        ):
            self.assertIn(marker, block, marker)

    def test_revert_dnsmasq_restores_or_converges_every_runtime_field(self):
        block = function_block(self.init, "revert_dnsmasq", "start_fail")
        for marker in (
            "dnsmasq_server=$(uci_get_config \"dnsmasq_server\")",
            "dnsmasq_noresolv=$(uci_get_config \"dnsmasq_noresolv\")",
            "dnsmasq_resolvfile=$(uci_get_config \"dnsmasq_resolvfile\")",
            "dnsmasq_cachesize=$(uci_get_config \"dnsmasq_cachesize\")",
            "dnsmasq_filter_aaaa=$(uci_get_config \"dnsmasq_filter_aaaa\")",
            "uci -q set dhcp.@dnsmasq[0].noresolv=0",
            "uci -q set dhcp.@dnsmasq[0].localuse=1",
            "uci -q set dhcp.@dnsmasq[0].cachesize=\"$dnsmasq_cachesize\"",
            "uci -q set dhcp.@dnsmasq[0].filter_aaaa=\"$dnsmasq_filter_aaaa\"",
            "uci -q delete openkill.config.dnsmasq_cachesize",
            "uci -q delete openkill.config.dnsmasq_filter_aaaa",
            "uci -q del openkill.config.dnsmasq_server",
            "uci -q commit dhcp",
            "uci -q commit openkill",
            "/etc/init.d/dnsmasq restart",
        ):
            self.assertIn(marker, block, marker)

        # Resolver backup metadata is read for restoration but is not deleted
        # by the production stop path.  Treating it as transient would make
        # the field-level gate reject the supported restart/recovery contract.
        for marker in (
            "uci -q delete openkill.config.dnsmasq_noresolv",
            "uci -q delete openkill.config.dnsmasq_resolvfile",
            "uci -q delete openkill.config.default_resolvfile",
            "uci -q delete openkill.config.redirect_dns",
            "uci -q delete openkill.config.cachesize_dns",
            "uci -q delete openkill.config.filter_aaaa_dns",
        ):
            self.assertNotIn(marker, block)

    def test_last_start_failed_is_transient_and_cleared_after_readiness(self):
        start_fail = function_block(self.init, "start_fail", "sub_info_set")
        readiness = self.init[self.init.index("check_core_status()") : self.init.index("start_run_core()")]
        self.assertIn("uci -q set openkill.config.last_start_failed=1", start_fail)
        self.assertIn("uci -q commit openkill", start_fail)
        self.assertIn("uci -q delete openkill.config.last_start_failed", readiness)
        self.assertIn("uci -q commit openkill", readiness)

    def test_config_path_only_changes_in_missing_target_fallback(self):
        choose = function_block(self.init, "config_choose", "config_check")
        self.assertIn("if [ -z \"$RAW_CONFIG_FILE\" ] || [ ! -f \"$RAW_CONFIG_FILE\" ]; then", choose)
        self.assertIn("uci -q set openkill.config.config_path=", choose)
        # The normal start order selects the already configured, existing file
        # before reading the rest of the config.  That path has no assignment.
        start = function_block(self.init, "start_service", "stop_service")
        order = 'RAW_CONFIG_FILE=$(uci_get_config "config_path")\n      config_choose\n      get_config'
        self.assertIn(order, start)
        normal_path = choose.split("if [ -z \"$RAW_CONFIG_FILE\" ] || [ ! -f \"$RAW_CONFIG_FILE\" ]; then", 1)[0]
        self.assertNotIn("uci -q set openkill.config.config_path=", normal_path)

    def test_get_config_commit_is_idempotent_and_start_order_is_explicit(self):
        get_config = function_block(self.init, "get_config", "start_service")
        self.assertIn('dns_port=$(uci_get_config "dns_port")', get_config)
        self.assertIn('uci -q set openkill.config.dns_port=7874', get_config)
        # A commit records the selected/defaulted state; the field-level gate
        # compares its semantic delta instead of treating the commit itself as
        # an unexpected user mutation.
        self.assertIn("uci -q commit openkill", get_config)
        start = function_block(self.init, "start_service", "stop_service")
        expected_order = (
            "openkill_config_normalize.sh",
            "check_run_quick\n         overwrite_file",
            "      config_choose\n      get_config\n      do_run_mode",
            "do_run_file \"$RAW_CONFIG_FILE\"",
        )
        positions = [start.index(marker) for marker in expected_order]
        self.assertEqual(positions, sorted(positions))

    def test_normalization_is_persistent_only_when_it_changes_values(self):
        self.assertIn("changed=0", self.normalize)
        self.assertIn('if [ "$changed" = 1 ]; then', self.normalize)
        self.assertIn("uci -q commit openkill", self.normalize)
        self.assertNotIn("uci -q commit dhcp", self.normalize)

    def test_firewall_include_is_lifecycle_owned_and_network_uci_is_untouched(self):
        prepare = function_block(self.init, "prepare_openkill_include", "remove_openkill_include")
        remove = function_block(self.init, "remove_openkill_include", "apply_node_endpoint_sets")
        for marker in (
            "uci -q set firewall.openkill=include",
            "uci -q set firewall.openkill.path=/var/etc/openkill.include",
            "uci -q commit firewall",
        ):
            self.assertIn(marker, prepare)
        self.assertIn("uci -q delete firewall.openkill", remove)
        self.assertIn("uci -q commit firewall", remove)
        self.assertNotRegex(
            self.init,
            r"uci(?: -q)?\s+(?:set|add|add_list|delete|del|del_list|commit|batch|import)[^\n]*\bnetwork\.",
        )

    def test_native_passwall_cleanup_is_conditional_and_documented(self):
        block = function_block(self.init, "sanitize_native_fw4_compat", "ensure_fw4_optional_include")
        self.assertIn('[ "$tun_owner" = "mihomo" ] || return 0', block)
        self.assertIn('[ -n "$FW4" ] || return 0', block)
        self.assertIn("uci -q get firewall.passwall.reload", block)
        self.assertIn("uci -q delete firewall.passwall.reload", block)
        self.assertIn("uci -q commit firewall", block)

    def test_subscription_and_age_metadata_are_non_default_user_paths(self):
        sub = function_block(self.init, "sub_info_set", "sub_info_get")
        self.assertIn("uci -q delete openkill.$section.url", sub)
        self.assertIn("uci -q add_list openkill.$section.url", sub)
        overwrite = function_block(self.init, "overwrite_file", "clear_overwrite_set")
        # overwrite_file precedes clear_overwrite_set in the source, so inspect
        # the complete function body directly when the helper ordering changes.
        overwrite = self.init[self.init.index("overwrite_file()") : self.init.index("get_config()")]
        self.assertIn("uci -q add openkill overwrite", overwrite)
        self.assertIn("uci -q add openkill subscribe_info", overwrite)
        self.assertIn("uci_set_age_keys_by_name", overwrite)

    def test_core_metadata_and_overwrite_are_explicit_lifecycle_state(self):
        core = (SHARE / "openkill_core.sh").read_text(encoding="utf-8")
        self.assertIn('uci -q set openkill.config.core_arch=', core)
        self.assertIn('uci -q set openkill.config.core_type="Meta"', core)
        clear = function_block(self.init, "clear_overwrite_set", "get_config")
        self.assertIn("uci -q delete openkill.@overwrite[0]", clear)
        self.assertIn("uci -q commit openkill", clear)

    def test_watchdog_repair_is_expected_dhcp_runtime_mutation(self):
        # The watchdog has one bounded, idempotent repair path.  It must keep
        # the same package ownership as change_dnsmasq rather than becoming an
        # untracked mutation.
        self.assertIn("uci -q del dhcp.@dnsmasq[-1].server", self.watchdog)
        self.assertIn('uci -q add_list dhcp.@dnsmasq[0].server=127.0.0.1#"$dns_port"', self.watchdog)
        self.assertIn("uci -q set dhcp.@dnsmasq[0].noresolv=1", self.watchdog)
        self.assertIn("uci -q commit dhcp", self.watchdog)
        self.assertIn("/etc/init.d/dnsmasq restart", self.watchdog)

    def test_package_lifecycle_keeps_user_conffile_and_does_not_delete_runtime_config(self):
        conffiles = self.makefile.split("define Package/$(PKG_NAME)/conffiles", 1)[1].split("endef", 1)[0]
        self.assertIn("/etc/config/openkill", conffiles)
        postrm = self.makefile.split("define Package/$(PKG_NAME)/postrm", 1)[1].split("endef", 1)[0]
        self.assertNotIn("/etc/config/openkill", postrm)
        self.assertNotRegex(postrm, r"rm\s+-rf\s+/etc/openkill(?:/|\s|$)")
        self.assertIn("/etc/init.d/openkill stop", self.makefile)
        self.assertIn("openkill_config_normalize.sh", self.makefile)

    def test_one_click_uninstall_is_separate_and_explicitly_destructive(self):
        # The operator installer has an intentional uninstall path.  It is
        # outside the start/stop contract and must not be selected for a
        # lifecycle validation or package update.
        start = self.installer.index("uninstall(){")
        end = self.installer.index("[ \"$ACTION\" = uninstall ]", start)
        uninstall = self.installer[start:end]
        self.assertIn("/etc/init.d/openkill stop", uninstall)
        self.assertIn("opkg remove luci-app-openkill", uninstall)
        self.assertIn("rm -f /etc/config/openkill", uninstall)

    def test_local_start_running_stop_model_preserves_user_fields_and_converges(self):
        original = {
            "openkill": {
                "enable": "1",
                "config_path": "/etc/openkill/config/3e2-safe.yaml",
                "user_option": "keep",
                "redirect_dns": "0",
                "cachesize_dns": "0",
                "filter_aaaa_dns": "0",
                # These saved resolver values already exist in the R2A
                # baseline and intentionally survive a formal stop.
                "dnsmasq_noresolv": "0",
                "dnsmasq_resolvfile": "/tmp/resolv.conf.auto",
                "default_resolvfile": "/tmp/resolv.conf.auto",
            },
            "dhcp": {
                "server": ["9.9.9.9", "1.1.1.1"],
                "noresolv": "0",
                "resolvfile": "/tmp/resolv.conf.auto",
                "localuse": "1",
                "cachesize": "150",
                "filter_aaaa": "1",
            },
        }
        running = apply_dnsmasq_model(original)
        self.assertEqual(running["openkill"]["enable"], "1")
        self.assertEqual(running["openkill"]["config_path"], original["openkill"]["config_path"])
        self.assertEqual(running["openkill"]["user_option"], "keep")
        self.assertEqual(running["dhcp"]["server"], ["127.0.0.1#7874"])
        self.assertEqual(running["dhcp"]["noresolv"], "1")
        self.assertEqual(running["dhcp"]["cachesize"], "0")
        stopped = revert_dnsmasq_model(running, original)
        self.assertEqual(stopped, original)

    def test_persistent_resolver_backup_metadata_is_explicit(self):
        self.assertEqual(
            PERSISTENT_BACKUP_METADATA,
            {"dnsmasq_noresolv", "dnsmasq_resolvfile", "default_resolvfile"},
        )
        self.assertEqual(
            REVERSIBLE_OPENKILL_BACKUPS,
            {"dnsmasq_server", "dnsmasq_cachesize", "dnsmasq_filter_aaaa"},
        )

    def test_no_start_path_network_uci_mutation(self):
        start = function_block(self.init, "start_service", "stop_service")
        self.assertNotRegex(start, r"uci(?: -q)?[^\n]*\bnetwork\.")
        self.assertNotRegex(start, r"uci(?: -q)?[^\n]*\bfirewall\.passwall\.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
