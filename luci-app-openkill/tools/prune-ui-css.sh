#!/bin/sh
# Remove UI styles for pages that are no longer part of OpenKill.
# This runs on the build host against the staging copy, so the source CSS can
# remain readable while the installed package does not carry dead OixCloud
# styles or their responsive overrides.
set -eu

css="${1:-}"
[ -n "$css" ] && [ -f "$css" ] || exit 0
tmp="${css}.prune.$$"

awk '
  BEGIN { skip = 0 }
  # SECTION 7 was the removed OixCloud page.
  /SECTION 7: oixcloud\.htm/ { skip = 1; next }
  skip && /SECTION 8: debug\.htm/ { skip = 0 }
  skip { next }

  # The login panel was appended between the log/update sections and has no
  # remaining template or controller route.
  /oixCloud login panel/ { skip = 1; next }
  skip && /SECTION 13: update\.htm/ { skip = 0 }
  skip { next }

  # These variables were only consumed by the removed card/login styles.
  /Card \(oixcloud legacy\)/ { skip = 1; next }
  skip && /Progress Bar/ { skip = 0 }
  skip { next }
  /OixCloud Dark/ { skip = 1; next }
  skip && /Tab \/ Radio/ { skip = 0 }
  skip { next }

  { print }
' "$css" > "$tmp"
mv "$tmp" "$css"
