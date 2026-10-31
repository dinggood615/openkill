#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SCRIPT="$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/naiveproxy-standalone.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
mkdir -p "$TMP/root/nodes" "$TMP/run" "$TMP/bin"
cat > "$TMP/bin/ss" <<'EOF'
#!/bin/sh
if [ -n "${NAIVE_TEST_LISTEN_PORT:-}" ]; then
    printf 'LISTEN 0 128 127.0.0.1:%s 0.0.0.0:*\n' "$NAIVE_TEST_LISTEN_PORT"
fi
EOF
chmod 700 "$TMP/bin/ss"

export NAIVEPROXY_ROOT="$TMP/root"
export NAIVEPROXY_RUN="$TMP/run"
export NAIVEPROXY_PORT_BASE=11080
export NAIVEPROXY_PORT_LIMIT=100
export PATH="$TMP/bin:$PATH"

printf 'node-1 11080\n' > "$TMP/root/ports"
[ "$(sh "$SCRIPT" port node-2)" = 11081 ]
grep -qx 'node-2 11081' "$TMP/root/ports"

# New allocations continue after the highest saved mapping instead of filling
# a deleted-node gap.
printf 'node-1 11080\nnode-3 11083\n' > "$TMP/root/ports"
[ "$(sh "$SCRIPT" port node-4)" = 11084 ]
grep -qx 'node-4 11084' "$TMP/root/ports"

# A foreign listener on the next sequential port is a hard conflict. The map
# must remain untouched; silently skipping to a different port is forbidden.
printf 'node-1 11080\nnode-2 11081\n' > "$TMP/root/ports"
cp "$TMP/root/ports" "$TMP/ports.before"
export NAIVE_TEST_LISTEN_PORT=11082
if sh "$SCRIPT" port node-3 >/dev/null 2>&1; then
    echo 'expected sequential port conflict to fail' >&2
    exit 1
fi
cmp -s "$TMP/ports.before" "$TMP/root/ports"

# Existing stable mappings are preserved even if lower numbers are free.
unset NAIVE_TEST_LISTEN_PORT
printf 'node-1 11080\nnode-2 11083\n' > "$TMP/root/ports"
[ "$(sh "$SCRIPT" port node-2)" = 11083 ]

echo 'Naive sequential port allocation passed.'
