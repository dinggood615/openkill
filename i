#!/bin/sh
# OpenKill short installer entry
# Keep this bootstrap independent from a single GitHub hostname: a router that
# cannot resolve raw.githubusercontent.com must still reach the full installer.
set -u

tmp="${TMPDIR:-/tmp}/openkill-installer.$$"
trap 'rm -f "$tmp"' EXIT HUP INT TERM

sources='
https://raw.githubusercontent.com/dinggood615/openkill/master/scripts/install-openkill.sh
https://fastly.jsdelivr.net/gh/dinggood615/openkill@master/scripts/install-openkill.sh
https://cdn.jsdelivr.net/gh/dinggood615/openkill@master/scripts/install-openkill.sh
https://testingcf.jsdelivr.net/gh/dinggood615/openkill@master/scripts/install-openkill.sh
'

for source in $sources; do
    rm -f "$tmp"
    if curl -fL --retry 1 --connect-timeout 8 --max-time 45 "$source" -o "$tmp" \
        && grep -qx '# OpenKill installer' "$tmp"; then
        exec sh "$tmp" "$@"
    fi
done

echo 'OpenKill installer download failed: no valid source is reachable.' >&2
exit 1
