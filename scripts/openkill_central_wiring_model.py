#!/usr/bin/env python3
"""Development-only model for guarded central NFT renderer activation.

This module describes the Phase 3D migration contract without wiring it into
OpenKill's runtime.  It is intentionally pure: all inputs are in-memory
values, no production shell is imported, and no subprocess, network, or file
mutation is performed.  The model is the executable companion to
``openkill-central-wiring-v1.json``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, Mapping, Tuple


CENTRAL_WIRING_SCHEMA = "OPENKILL_CENTRAL_WIRING_V1"
CENTRAL_WIRING_VERSION = 1
SEMANTIC_SPEC_VERSION = 1
CLASSIFIER_CONTRACT_VERSION = 1
SHADOW_STATE_SCHEMA_VERSION = 1
NFT_IR_VERSION = 1
OWNERSHIP_MANIFEST_VERSION = 1
MARK_ABI_VERSION = 1
DEFAULT_PRODUCTION_PROFILE = "current"
DEFAULT_ENGINE_MODE = "legacy"

ENGINE_MODES: Tuple[str, ...] = ("legacy", "shadow", "central")
WIRING_STATES: Tuple[str, ...] = (
    "LEGACY_AUTHORITATIVE",
    "SHADOW_COMPARE",
    "CENTRAL_PRECHECK",
    "CENTRAL_ACTIVE",
    "ROLLBACK",
    "BLOCKED",
)
PROFILES: Tuple[str, ...] = ("current", "target")
OWNERS: Tuple[str, ...] = ("OPENKILL", "MIHOMO", "DISABLED", "UNKNOWN")

MARK_ABI = {
    "version": MARK_ABI_VERSION,
    "mark": "0x162",
    "mask": "0xffffffff",
    "route_table": 354,
    "rule_preference": 1888,
}

# The graph deliberately keeps the migration through CENTRAL_PRECHECK and
# ROLLBACK explicit.  A stable state is a valid no-op transition; all other
# edges must appear here before a caller may use them.
ALLOWED_TRANSITIONS = {
    "LEGACY_AUTHORITATIVE": frozenset({"LEGACY_AUTHORITATIVE", "SHADOW_COMPARE"}),
    "SHADOW_COMPARE": frozenset({"SHADOW_COMPARE", "LEGACY_AUTHORITATIVE", "CENTRAL_PRECHECK", "BLOCKED"}),
    "CENTRAL_PRECHECK": frozenset({"CENTRAL_PRECHECK", "CENTRAL_ACTIVE", "SHADOW_COMPARE", "BLOCKED"}),
    "CENTRAL_ACTIVE": frozenset({"CENTRAL_ACTIVE", "SHADOW_COMPARE", "ROLLBACK", "BLOCKED"}),
    "ROLLBACK": frozenset({"ROLLBACK", "LEGACY_AUTHORITATIVE", "SHADOW_COMPARE", "BLOCKED"}),
    "BLOCKED": frozenset({"BLOCKED", "LEGACY_AUTHORITATIVE", "SHADOW_COMPARE"}),
}

MODE_FOR_STATE = {
    "LEGACY_AUTHORITATIVE": "legacy",
    "SHADOW_COMPARE": "shadow",
    "CENTRAL_PRECHECK": "central",
    "CENTRAL_ACTIVE": "central",
    "ROLLBACK": "central",
    "BLOCKED": "legacy",
}

FAILURE_CLASSES: Tuple[str, ...] = (
    "PRECHECK_FAIL",
    "NFT_CHECK_FAIL",
    "APPLY_FAIL",
    "POST_VERIFY_FAIL",
    "MANIFEST_COMMIT_FAIL",
    "OLD_FALLBACK_FAIL",
)


class WiringValidationError(ValueError):
    """Raised when a development wiring model is malformed or unsafe."""


def _require_one_of(value: Any, allowed: Iterable[str], label: str) -> str:
    if not isinstance(value, str) or value not in tuple(allowed):
        raise WiringValidationError("unknown {}: {!r}".format(label, value))
    return value


def profile_allowed(profile: str, *, production: bool = True, development_preview: bool = False) -> bool:
    """Return whether a profile can be used for the requested design path."""

    if profile not in PROFILES:
        return False
    if production:
        return profile == DEFAULT_PRODUCTION_PROFILE
    if profile == "target" and not development_preview:
        return False
    return True


def validate_transition(
    source: str,
    target: str,
    *,
    eligibility_pass: bool = False,
) -> Dict[str, Any]:
    """Validate one explicit state-machine edge.

    The only edge that can grant a central writer is
    ``CENTRAL_PRECHECK -> CENTRAL_ACTIVE`` and it requires a completed
    eligibility evaluation.  An invalid edge is rejected rather than being
    coerced into a fallback state.
    """

    _require_one_of(source, WIRING_STATES, "source state")
    _require_one_of(target, WIRING_STATES, "target state")
    allowed = target in ALLOWED_TRANSITIONS[source]
    if not allowed:
        raise WiringValidationError("illegal transition: {} -> {}".format(source, target))
    if source == "CENTRAL_PRECHECK" and target == "CENTRAL_ACTIVE" and not eligibility_pass:
        raise WiringValidationError("central activation requires a passing eligibility gate")
    return {
        "valid": True,
        "source": source,
        "target": target,
        "writer_grant": target == "CENTRAL_ACTIVE",
        "requires_eligibility": source == "CENTRAL_PRECHECK" and target == "CENTRAL_ACTIVE",
    }


def writer_policy(mode: str, *, central_eligible: bool = False) -> Dict[str, Any]:
    """Describe which side may mutate the dataplane in one wiring mode."""

    _require_one_of(mode, ENGINE_MODES, "engine mode")
    if mode == "legacy":
        return {
            "mode": mode,
            "old_can_write": True,
            "new_can_write": False,
            "new_can_compute": False,
            "runtime_writer": "legacy",
            "blocked": False,
        }
    if mode == "shadow":
        return {
            "mode": mode,
            "old_can_write": True,
            "new_can_write": False,
            "new_can_compute": True,
            "runtime_writer": "legacy",
            "blocked": False,
        }
    # Central is fail-closed until every precondition has passed.  Ineligible
    # central mode has no writer; callers must return to legacy/shadow.
    return {
        "mode": mode,
        "old_can_write": False,
        "new_can_write": bool(central_eligible),
        "new_can_compute": bool(central_eligible),
        "runtime_writer": "central" if central_eligible else "none",
        "blocked": not bool(central_eligible),
    }


def single_writer_valid(policy: Mapping[str, Any]) -> bool:
    """Check the hard single-writer invariant for a writer policy."""

    writers = int(bool(policy.get("old_can_write"))) + int(bool(policy.get("new_can_write")))
    runtime_writer = policy.get("runtime_writer")
    if writers > 1 or runtime_writer not in {"legacy", "central", "none"}:
        return False
    if writers == 0:
        return runtime_writer == "none"
    if policy.get("old_can_write"):
        return runtime_writer == "legacy"
    return runtime_writer == "central"


def _check_equal(
    facts: Mapping[str, Any],
    key: str,
    expected: Any,
    checks: Dict[str, bool],
    blockers: list[str],
    blocker: str,
) -> None:
    if key not in facts:
        checks[key] = False
        blockers.append("UNKNOWN_" + key.upper())
        return
    checks[key] = facts[key] == expected
    if not checks[key]:
        blockers.append(blocker)


def _check_bool(
    facts: Mapping[str, Any],
    key: str,
    expected: bool,
    checks: Dict[str, bool],
    blockers: list[str],
    blocker: str,
) -> None:
    if key not in facts or not isinstance(facts[key], bool):
        checks[key] = False
        blockers.append("UNKNOWN_" + key.upper())
        return
    checks[key] = facts[key] is expected
    if not checks[key]:
        blockers.append(blocker)


def evaluate_eligibility(facts: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate all guarded central activation requirements.

    Missing, malformed, or unknown inputs are blockers.  The function never
    supplies a development default for a production fact.
    """

    if not isinstance(facts, Mapping):
        raise WiringValidationError("eligibility facts must be a mapping")
    checks: Dict[str, bool] = {}
    blockers: list[str] = []
    _check_bool(facts, "fw4_present", True, checks, blockers, "FW4_MISSING")
    _check_bool(facts, "nft_capability_supported", True, checks, blockers, "NFT_CAPABILITY_UNSUPPORTED")
    _check_equal(facts, "backend", "modern_fw4_nft", checks, blockers, "LEGACY_BACKEND")
    _check_equal(facts, "owner", "OPENKILL", checks, blockers, "OWNER_NOT_OPENKILL")
    _check_equal(facts, "profile", DEFAULT_PRODUCTION_PROFILE, checks, blockers, "PROFILE_NOT_CURRENT")
    _check_equal(facts, "semantic_spec_version", SEMANTIC_SPEC_VERSION, checks, blockers, "SEMANTIC_VERSION_UNKNOWN")
    _check_equal(facts, "classifier_contract_version", CLASSIFIER_CONTRACT_VERSION, checks, blockers, "CLASSIFIER_VERSION_UNKNOWN")
    _check_equal(facts, "shadow_state_schema_version", SHADOW_STATE_SCHEMA_VERSION, checks, blockers, "SHADOW_SCHEMA_UNKNOWN")
    _check_equal(facts, "nft_ir_version", NFT_IR_VERSION, checks, blockers, "NFT_IR_VERSION_UNKNOWN")
    _check_equal(facts, "manifest_version", OWNERSHIP_MANIFEST_VERSION, checks, blockers, "MANIFEST_VERSION_UNKNOWN")
    _check_bool(facts, "current_state_supported", True, checks, blockers, "CURRENT_STATE_UNSUPPORTED")
    _check_bool(facts, "bc07_active", False, checks, blockers, "BC07_UNSUPPORTED")
    _check_bool(facts, "explicit_policy_unresolved", False, checks, blockers, "EXPLICIT_POLICY_UNRESOLVED")
    _check_bool(facts, "bc02_current_order_verified", True, checks, blockers, "BC02_ORDER_NOT_VERIFIED")
    _check_bool(facts, "bc03_current_order_preserved", True, checks, blockers, "BC03_ORDER_NOT_PRESERVED")
    _check_bool(facts, "bc04_current_gap_preserved", True, checks, blockers, "BC04_GAP_NOT_PRESERVED")
    _check_bool(facts, "bc05_diagnostic_only", True, checks, blockers, "BC05_ACTION_GUARD_FAILED")
    _check_bool(facts, "bc06_diagnostic_only", True, checks, blockers, "BC06_ACTION_GUARD_FAILED")
    _check_bool(facts, "nft_check_pass", True, checks, blockers, "NFT_CHECK_FAILED")
    _check_bool(facts, "runtime_healthy", True, checks, blockers, "RUNTIME_UNHEALTHY")
    _check_bool(facts, "owner_transition", False, checks, blockers, "OWNER_TRANSITION_PENDING")
    _check_bool(facts, "pending_fw4_reconcile", False, checks, blockers, "FW4_RECONCILE_PENDING")
    _check_bool(facts, "component_failure", False, checks, blockers, "COMPONENT_FAILURE")
    _check_bool(facts, "restart_required", False, checks, blockers, "RESTART_REQUIRED")
    _check_bool(facts, "same_name_foreign_collision", False, checks, blockers, "FOREIGN_NAME_COLLISION")
    _check_bool(facts, "listener_ports_valid", True, checks, blockers, "LISTENER_PORTS_INVALID")
    _check_bool(facts, "watchdog_single_writer_ready", True, checks, blockers, "WATCHDOG_DIRECT_WRITER")
    _check_bool(facts, "fw4_worker_single_writer_ready", True, checks, blockers, "FW4_WORKER_DIRECT_WRITER")
    _check_bool(facts, "no_old_writer_active", True, checks, blockers, "OLD_WRITER_STILL_ACTIVE")
    _check_bool(facts, "manifest_ready", True, checks, blockers, "MANIFEST_NOT_READY")

    mark_abi = facts.get("mark_abi")
    checks["mark_abi"] = isinstance(mark_abi, Mapping) and dict(mark_abi) == MARK_ABI
    if not checks["mark_abi"]:
        blockers.append("MARK_ABI_MISMATCH")

    # Deduplicate while preserving evidence order, so reports are stable.
    blockers = list(dict.fromkeys(blockers))
    return {
        "eligible": not blockers,
        "checks": checks,
        "blockers": blockers,
        "profile": facts.get("profile"),
        "owner": facts.get("owner"),
    }


def central_renderer_eligible(facts: Mapping[str, Any]) -> bool:
    """Boolean convenience API for a future gate caller."""

    return bool(evaluate_eligibility(facts)["eligible"])


FAILURE_ACTIONS: Dict[str, Dict[str, Any]] = {
    "PRECHECK_FAIL": {
        "runtime_untouched": True,
        "old_authority_unchanged": True,
        "next_state": "BLOCKED",
        "action": "remain_or_return_legacy",
    },
    "NFT_CHECK_FAIL": {
        "runtime_untouched": True,
        "old_authority_unchanged": True,
        "next_state": "BLOCKED",
        "action": "remain_or_return_legacy",
    },
    "APPLY_FAIL": {
        "runtime_untouched": False,
        "old_authority_unchanged": "if_atomic_else_restore",
        "next_state": "ROLLBACK",
        "action": "verify_atomicity_then_rollback",
    },
    "POST_VERIFY_FAIL": {
        "runtime_untouched": False,
        "old_authority_unchanged": False,
        "next_state": "ROLLBACK",
        "action": "rollback_owned_state_then_fallback_old",
    },
    "MANIFEST_COMMIT_FAIL": {
        "runtime_untouched": False,
        "old_authority_unchanged": False,
        "next_state": "BLOCKED",
        "action": "freeze_activation_and_recover_manifest",
    },
    "OLD_FALLBACK_FAIL": {
        "runtime_untouched": False,
        "old_authority_unchanged": False,
        "next_state": "BLOCKED",
        "action": "bounded_escalation_without_retry_loop",
    },
}


def failure_action(failure_class: str) -> Dict[str, Any]:
    _require_one_of(failure_class, FAILURE_CLASSES, "failure class")
    return dict(FAILURE_ACTIONS[failure_class])


def ownership_transition(from_owner: str, to_owner: str) -> Dict[str, Any]:
    """Return the guarded writer handoff policy for owner changes."""

    _require_one_of(from_owner, OWNERS, "from owner")
    _require_one_of(to_owner, OWNERS, "to owner")
    if from_owner == to_owner == "OPENKILL":
        return {"allowed": True, "action": "NO_CHANGE", "writer": "OPENKILL"}
    if to_owner in {"MIHOMO", "DISABLED"}:
        return {"allowed": False, "action": "BLOCK_CENTRAL", "writer": "NONE"}
    if from_owner == "MIHOMO" and to_owner == "OPENKILL":
        return {"allowed": False, "action": "REQUIRE_EXPLICIT_REACQUISITION", "writer": "NONE"}
    return {"allowed": False, "action": "FAIL_CLOSED_UNKNOWN_OWNER", "writer": "NONE"}


def source_drift_ok(current: Mapping[str, str], baseline: Mapping[str, str]) -> bool:
    """Migration-time guard: exact production function hashes must match."""

    if not isinstance(current, Mapping) or not isinstance(baseline, Mapping):
        return False
    if not current or not baseline:
        return False
    return dict(current) == dict(baseline) and all(
        isinstance(value, str) and len(value) == 64 for value in current.values()
    )


def canonical_json(value: Any) -> str:
    """Serialize a value without timestamps, random IDs, or order drift."""

    volatile = {"timestamp", "pid", "random_id", "temporary_path"}

    def clean(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {key: clean(val) for key, val in item.items() if key not in volatile}
        if isinstance(item, list):
            return [clean(val) for val in item]
        if isinstance(item, tuple):
            return [clean(val) for val in item]
        return item

    return json.dumps(clean(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def desired_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def payload_hash(payload: str) -> str:
    if not isinstance(payload, str):
        raise WiringValidationError("apply payload must be text")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_wiring_fixture(data: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate the machine-readable design fixture and return it unchanged."""

    if not isinstance(data, Mapping):
        raise WiringValidationError("wiring fixture must be an object")
    if data.get("schema") != CENTRAL_WIRING_SCHEMA or data.get("version") != CENTRAL_WIRING_VERSION:
        raise WiringValidationError("unknown wiring schema version")
    versions = data.get("versions")
    expected = {
        "semantic_spec": SEMANTIC_SPEC_VERSION,
        "classifier_contract": CLASSIFIER_CONTRACT_VERSION,
        "shadow_state_schema": SHADOW_STATE_SCHEMA_VERSION,
        "nft_ir": NFT_IR_VERSION,
        "ownership_manifest": OWNERSHIP_MANIFEST_VERSION,
        "mark_abi": MARK_ABI_VERSION,
    }
    if versions != expected:
        raise WiringValidationError("wiring dependency version mismatch")
    if data.get("mark_abi") != MARK_ABI:
        raise WiringValidationError("mark ABI drift")
    if data.get("default_engine") != DEFAULT_ENGINE_MODE or data.get("default_state") != "LEGACY_AUTHORITATIVE":
        raise WiringValidationError("production default must remain legacy")
    if tuple(data.get("engine_modes", ())) != ENGINE_MODES:
        raise WiringValidationError("engine mode enum drift")
    if tuple(data.get("states", ())) != WIRING_STATES:
        raise WiringValidationError("wiring state enum drift")
    if set(data.get("failure_classes", ())) != set(FAILURE_CLASSES):
        raise WiringValidationError("failure class enum drift")
    return data


__all__ = [
    "ALLOWED_TRANSITIONS",
    "CENTRAL_WIRING_SCHEMA",
    "CENTRAL_WIRING_VERSION",
    "DEFAULT_ENGINE_MODE",
    "DEFAULT_PRODUCTION_PROFILE",
    "ENGINE_MODES",
    "FAILURE_CLASSES",
    "MARK_ABI",
    "MODE_FOR_STATE",
    "OWNERS",
    "PROFILES",
    "WIRING_STATES",
    "WiringValidationError",
    "canonical_json",
    "central_renderer_eligible",
    "desired_hash",
    "evaluate_eligibility",
    "failure_action",
    "ownership_transition",
    "payload_hash",
    "profile_allowed",
    "single_writer_valid",
    "source_drift_ok",
    "validate_transition",
    "validate_wiring_fixture",
    "writer_policy",
]
