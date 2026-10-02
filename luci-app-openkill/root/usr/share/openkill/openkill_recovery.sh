#!/bin/sh
# Root-only snapshots: generated YAML and the matching OpenKill UCI state.
set -eu
umask 077
checkpoint=/etc/openkill/.last-good
token_file=/tmp/openkill-start.token
recovery_state=/tmp/openkill-recovery.state
write_recovery_state() {
    reason="$1"
    tmp="${recovery_state}.$$"
    printf 'status=failed\nreason=%s\nchecked_at=%s\n' "$reason" "$(date +%s)" > "$tmp" 2>/dev/null && mv -f "$tmp" "$recovery_state" 2>/dev/null
    rm -f "$tmp"
}
recover_fail() {
    write_recovery_state "$1"
    exit 1
}
case "${1:-}" in
  save)
    file="$2"
    [ -s "$file" ] && [ -s /etc/config/openkill ] || exit 1
    stage=$(mktemp -d /etc/openkill/.checkpoint.XXXXXX)
    trap 'rm -f "$stage/config.yaml" "$stage/config.uci" "$stage/core.sha256"; rmdir "$stage" 2>/dev/null || true' EXIT
    cp "$file" "$stage/config.yaml"
    cp /etc/config/openkill "$stage/config.uci"
    sha256sum /etc/openkill/clash | awk '{print $1}' > "$stage/core.sha256"
    old=$(readlink "$checkpoint" 2>/dev/null || true)
    ln -s "$stage" "$checkpoint.new.$$"
    mv -Tf "$checkpoint.new.$$" "$checkpoint"
    trap - EXIT
    case "$old" in
      /etc/openkill/.checkpoint.*)
        [ "$old" = "$stage" ] || {
          rm -f "$old/config.yaml" "$old/config.uci" "$old/core.sha256"
          rmdir "$old" 2>/dev/null || true
        } ;;
    esac
    ;;
  restore)
    expected="$2"
    # Let rc.common finish its procd transaction before requesting a stop.
    sleep 2
    [ "$(cat "$token_file" 2>/dev/null)" = "$expected" ] || exit 0
    [ -s "$checkpoint/config.yaml" ] && [ -s "$checkpoint/config.uci" ] || recover_fail checkpoint-missing
    # Cleared only by an explicit fresh start, never by an automatic retry.
    mkdir /tmp/openkill-recovery.once 2>/dev/null || recover_fail recovery-already-attempted
    current=$(sha256sum /etc/openkill/clash | awk '{print $1}')
    saved=$(cat "$checkpoint/core.sha256")
    # A snapshot is only valid for its verified core. Do not silently roll
    # a configuration back across an unverified core upgrade.
    if [ "$current" != "$saved" ]; then
        target=$(readlink -f /etc/openkill/clash)
        previous="$target.previous"
        [ -s "$previous" ] || recover_fail prior-core-missing
        [ "$(sha256sum "$previous" | awk '{print $1}')" = "$saved" ] || recover_fail prior-core-mismatch
        candidate="$previous"
    else
        candidate=/etc/openkill/clash
    fi
    SAFE_PATHS=/usr/share/openkill:/etc/ssl:/tmp "$candidate" -t -d /etc/openkill -f "$checkpoint/config.yaml" >/tmp/openkill-recovery-check.log 2>&1 || recover_fail checkpoint-config-invalid
    [ "$(cat "$token_file" 2>/dev/null)" = "$expected" ] || exit 0
    /etc/init.d/openkill stop
    if [ "$candidate" != /etc/openkill/clash ]; then
        cp -p "$candidate" "$target.recovery"
        mv -f "$target.recovery" "$target"
    fi
    cp "$checkpoint/config.uci" /etc/config/openkill.recovery
    mv -f /etc/config/openkill.recovery /etc/config/openkill
    OPENKILL_RECOVERY=1 /etc/init.d/openkill start || recover_fail recovered-start-rejected
    ;;
  *) exit 2 ;;
esac
