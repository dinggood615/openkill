#!/bin/sh
# OpenKill short installer entry
set -eu

base='https://raw.githubusercontent.com/dinggood615/openkill/master/scripts/install-openkill.sh'
tmp="${TMPDIR:-/tmp}/openkill-installer.$$"
trap 'rm -f "$tmp"' EXIT HUP INT TERM

curl -fsSL --retry 2 --connect-timeout 8 --max-time 60 "$base" -o "$tmp"
exec sh "$tmp" "$@"
