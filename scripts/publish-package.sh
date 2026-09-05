#!/bin/bash
set -euo pipefail
: "${RELEASE_VERSION:?}" "${PACKAGE_FORMAT:?}" "${GITHUB_REPOSITORY:?}" "${GITHUB_SHA:?}"
case "$PACKAGE_FORMAT" in ipk|apk) ;; *) exit 1;; esac
mapfile -t packages < <(find tmp/SDK/bin -type f -name "luci-app-openkill*.$PACKAGE_FORMAT")
[ "${#packages[@]}" -eq 1 ] || { echo "Expected exactly one package"; exit 1; }
asset="luci-app-openkill_${RELEASE_VERSION}_all.$PACKAGE_FORMAT"
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
python3 - <<'PY'
import os, json, hashlib, pathlib
p = pathlib.Path(os.environ["STAGE"]) / os.environ["ASSET"]
data = dict(version=os.environ["RELEASE_VERSION"], format=os.environ["PACKAGE_FORMAT"],
            architecture="all", commit=os.environ["GITHUB_SHA"], filename=p.name,
            sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
            url=f'https://github.com/{os.environ["GITHUB_REPOSITORY"]}/releases/download/v{os.environ["RELEASE_VERSION"]}-{os.environ["PACKAGE_FORMAT"]}/{p.name}')
(p.parent / "latest.json").write_text(json.dumps(data) + "\n")
PY
gh auth setup-git
git clone --depth 1 --branch package "https://github.com/$GITHUB_REPOSITORY.git" "$stage/channel"
cd "$stage/channel"
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
