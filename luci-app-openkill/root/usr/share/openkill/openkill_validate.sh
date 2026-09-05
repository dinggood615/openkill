#!/bin/sh
# Validate a generated OpenKill/Mihomo configuration before it replaces the
# last known-good file.  This script is intentionally small so it also works
# on BusyBox based OpenWrt images.

CONFIG_FILE="${1:-}"
CORE="${2:-/etc/openkill/clash}"

[ -n "$CONFIG_FILE" ] || {
   echo "configuration path is required" >&2
   exit 2
}
[ -s "$CONFIG_FILE" ] || {
   echo "configuration file is missing or empty: $CONFIG_FILE" >&2
   exit 2
}

# Psych is the YAML implementation shipped by the OpenWrt Ruby packages.
# Loading only (without rewriting) catches malformed YAML before the running
# core is touched.
if command -v ruby >/dev/null 2>&1; then
   ruby -ryaml -e 'YAML.load_file(ARGV[0]); exit 0' "$CONFIG_FILE" >/dev/null 2>&1 || {
      echo "YAML parse failed: $CONFIG_FILE" >&2
      exit 3
   }
fi

# Mihomo's -t performs the official config validation without opening the
# listeners.  The installer replaces old cores that do not expose this flag.
if [ -x "$CORE" ]; then
   "$CORE" -t -d "$(dirname "$CONFIG_FILE")" -f "$CONFIG_FILE" >/tmp/openkill-config-test.$$.log 2>&1 || {
      cat /tmp/openkill-config-test.$$.log >&2
      rm -f /tmp/openkill-config-test.$$.log
      exit 4
   }
   rm -f /tmp/openkill-config-test.$$.log
fi

exit 0
