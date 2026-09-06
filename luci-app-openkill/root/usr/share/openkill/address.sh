#!/bin/sh
# Shared by YAML generation and controller checks. Never evaluate input.
openkill_bind_address() {
    local address="${1:-lan}"
    [ "$address" != lan ] || address="$(uci -q get network.lan.ipaddr 2>/dev/null)"
    address="${address%%/*}"
    address="${address#\[}"; address="${address%\]}"
    case "$address" in
        ''|*[!0-9a-fA-F.:]*) address=127.0.0.1 ;;
    esac
    case "$address" in
        *:*) ;;
        *) printf '%s\n' "$address" | awk -F. 'NF != 4 {exit 1} {for(i=1;i<=4;i++) if($i !~ /^[0-9]+$/ || $i>255) exit 1}' || address=127.0.0.1 ;;
    esac
    printf '%s' "$address"
}

openkill_local_address() {
    local address
    address="$(openkill_bind_address "$1")"
    case "$address" in 0.0.0.0) address=127.0.0.1 ;; ::) address=::1 ;; esac
    printf '%s' "$address"
}
