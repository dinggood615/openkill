#!/bin/bash
set -euo pipefail
: "${RELEASE_VERSION:?}" "${PACKAGE_FORMAT:?}" "${GITHUB_REPOSITORY:?}" "${GITHUB_SHA:?}"
case "$PACKAGE_FORMAT" in ipk|apk) ;; *) exit 1;; esac
mapfile -t packages < <(find tmp/SDK/bin -type f -name "luci-app-openkill*.$PACKAGE_FORMAT")
[ "${#packages[@]}" -eq 1 ] || { echo "Expected exactly one package"; exit 1; }
# APK's package database requires dotted numeric versions; keep the public
# OpenKill version unchanged in the release manifest.
package_version="$RELEASE_VERSION"
[ "$PACKAGE_FORMAT" = apk ] && package_version="${RELEASE_VERSION/-/.}"
asset="luci-app-openkill_${package_version}_all.$PACKAGE_FORMAT"
stage=$(mktemp -d)
cp "${packages[0]}" "$stage/$asset"
tag="v${RELEASE_VERSION}-$PACKAGE_FORMAT"
if gh release view "$tag" --repo "$GITHUB_REPOSITORY" >/dev/null 2>&1; then
  # Published artifacts are immutable; a retry must reproduce the same bytes.
  gh release download "$tag" --repo "$GITHUB_REPOSITORY" --pattern "$asset" --dir "$stage/existing"
  cmp "$stage/$asset" "$stage/existing/$asset"
else
  gh release create "$tag" "$stage/$asset" --repo "$GITHUB_REPOSITORY" --target "$GITHUB_SHA" --latest=false --title "OpenKill $RELEASE_VERSION ($PACKAGE_FORMAT)" --notes "Source: $GITHUB_SHA. Independently verified $PACKAGE_FORMAT build."
fi
gh release download "$tag" --repo "$GITHUB_REPOSITORY" --pattern "$asset" --dir "$stage/verify"
cmp "$stage/$asset" "$stage/verify/$asset"
export ASSET="$asset" STAGE="$stage"
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  command -v python3 >/dev/null 2>&1 && PYTHON_BIN=python3 || PYTHON_BIN=python
fi
"$PYTHON_BIN" - <<'PY'
import os, json, hashlib, pathlib
p = pathlib.Path(os.environ["STAGE"]) / os.environ["ASSET"]
data = dict(version=os.environ["RELEASE_VERSION"], format=os.environ["PACKAGE_FORMAT"],
            architecture="all", commit=os.environ["GITHUB_SHA"], filename=p.name,
            sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
            url=f'https://github.com/{os.environ["GITHUB_REPOSITORY"]}/releases/download/v{os.environ["RELEASE_VERSION"]}-{os.environ["PACKAGE_FORMAT"]}/{p.name}')
(p.parent / "latest.json").write_text(json.dumps(data) + "\n")
PY
gh auth setup-git
channel_url="https://github.com/$GITHUB_REPOSITORY.git"
if git ls-remote --exit-code --heads "$channel_url" package >/dev/null 2>&1; then
  git clone --filter=blob:none --no-checkout --depth 1 --branch package "$channel_url" "$stage/channel"
else
  # The package channel may be intentionally empty after a release purge.
  # Create it as an orphan branch so the first verified package can recreate
  # the channel without requiring a manual placeholder commit.
  git init "$stage/channel"
  git -C "$stage/channel" remote add origin "$channel_url"
  git -C "$stage/channel" checkout --orphan package
  git -C "$stage/channel" config user.name 'github-actions[bot]'
  git -C "$stage/channel" config user.email 'github-actions[bot]@users.noreply.github.com'
fi
cd "$stage/channel"
# The channel also contains hundreds of megabytes of historical packages.
# Only this format's metadata and new asset are needed for publication.
git sparse-checkout set --no-cone "/master/latest-$PACKAGE_FORMAT.json" "/master/version" "/master/$asset"
git checkout
git config user.name 'github-actions[bot]'
git config user.email 'github-actions[bot]@users.noreply.github.com'
mkdir -p master
# Each format owns its manifest, avoiding IPK/APK publication conflicts.
cp "$stage/latest.json" "master/latest-$PACKAGE_FORMAT.json"
cp "$stage/$asset" "master/$asset"
if [ "$PACKAGE_FORMAT" = ipk ]; then
  printf 'v%s\n' "$RELEASE_VERSION" > master/version
fi
git add "master/latest-$PACKAGE_FORMAT.json"
git add -f "master/$asset"
[ "$PACKAGE_FORMAT" != ipk ] || git add master/version
git diff --cached --quiet && exit 0
git commit -m "Publish $RELEASE_VERSION $PACKAGE_FORMAT from $GITHUB_SHA"
for attempt in 1 2 3 4 5; do
  git push origin HEAD:package && exit 0
  git pull --rebase origin package
done
echo "Channel publication failed" >&2
exit 1
