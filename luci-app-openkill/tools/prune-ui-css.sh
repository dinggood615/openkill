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
  BEGIN { skip_section = 0; skip_login = 0; skip_card = 0; skip_dark = 0; skip_oix_responsive = 0 }
  # Each retired block has its own state.  Keeping the states separate avoids
  # an earlier block suppressing the reset marker for a later block.
  /SECTION 7: oixcloud\.htm/ { skip_section = 1; next }
  skip_section { if (/SECTION 8: debug\.htm/) skip_section = 0; else next }

  # The login panel was appended between the log/update sections and has no
  # remaining template or controller route.
  /oixCloud login panel/ { skip_login = 1; next }
  skip_login { if (/SECTION 13: update\.htm/) skip_login = 0; else next }

  # These variables were only consumed by the removed card/login styles.
  /Card \(oixcloud legacy\)/ { skip_card = 1; next }
  skip_card { if (/Progress Bar/) skip_card = 0; else next }
  /OixCloud Dark/ { skip_dark = 1; next }
  skip_dark { if (/Tab \/ Radio/) skip_dark = 0; else next }

  /\/\* oixcloud\.htm \*\// { skip_oix_responsive = 1; next }
  skip_oix_responsive { if (/\/\* update\.htm \*\//) skip_oix_responsive = 0; else next }

  { print }
' "$css" > "$tmp"
mv "$tmp" "$css"
