#!/bin/sh
# Root-only snapshots: generated YAML and the matching OpenKill UCI state.
set -eu
umask 077
checkpoint=/etc/openkill/.last-good
token_file=/tmp/openkill-start.token
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
    [ -s "$checkpoint/config.yaml" ] && [ -s "$checkpoint/config.uci" ] || exit 1
    # Cleared only by an explicit fresh start, never by an automatic retry.
    mkdir /tmp/openkill-recovery.once 2>/dev/null || exit 1
    current=$(sha256sum /etc/openkill/clash | awk '{print $1}')
    saved=$(cat "$checkpoint/core.sha256")
    # A snapshot is only valid for its verified core. Do not silently roll
    # a configuration back across an unverified core upgrade.
    if [ "$current" != "$saved" ]; then
        target=$(readlink -f /etc/openkill/clash)
        previous="$target.previous"
        [ -s "$previous" ] || exit 1
        [ "$(sha256sum "$previous" | awk '{print $1}')" = "$saved" ] || exit 1
        candidate="$previous"
    else
        candidate=/etc/openkill/clash
    fi
    SAFE_PATHS=/usr/share/openkill:/etc/ssl:/tmp "$candidate" -t -d /etc/openkill -f "$checkpoint/config.yaml" >/tmp/openkill-recovery-check.log 2>&1 || exit 1
    [ "$(cat "$token_file" 2>/dev/null)" = "$expected" ] || exit 0
    /etc/init.d/openkill stop
    if [ "$candidate" != /etc/openkill/clash ]; then
        cp -p "$candidate" "$target.recovery"
        mv -f "$target.recovery" "$target"
    fi
    cp "$checkpoint/config.uci" /etc/config/openkill.recovery
    mv -f /etc/config/openkill.recovery /etc/config/openkill
    OPENKILL_RECOVERY=1 /etc/init.d/openkill start
    ;;
  *) exit 2 ;;
esac
