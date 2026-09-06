#!/bin/bash
set -euo pipefail
: "${RELEASE_VERSION:?}" "${GITHUB_REPOSITORY:?}" "${GITHUB_TOKEN:?}"

export GH_TOKEN="$GITHUB_TOKEN"
keep_prefix="v${RELEASE_VERSION}-"

echo "Removing releases older than $RELEASE_VERSION"
while IFS=$'\t' read -r tag; do
  [ -n "$tag" ] || continue
  case "$tag" in
    "$keep_prefix"*) ;;
    *)
      gh release delete "$tag" --repo "$GITHUB_REPOSITORY" --yes >/dev/null 2>&1 || true
      gh api -X DELETE "repos/$GITHUB_REPOSITORY/git/refs/tags/$tag" >/dev/null 2>&1 || true
      echo "removed release $tag"
      ;;
  esac
done < <(gh api --paginate "repos/$GITHUB_REPOSITORY/releases?per_page=100" --jq '.[] | [.tag_name] | @tsv')

# Keep only packages belonging to the current version in the package channel.
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
git clone --depth 1 --branch package "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" "$stage/channel"
cd "$stage/channel"
changed=0
if [ -d master ]; then
  while IFS= read -r file; do
    base=$(basename "$file")
    keep=0
    case "$base" in
      "luci-app-openkill_${RELEASE_VERSION}_all.ipk"|"luci-app-openkill_${RELEASE_VERSION/-/.}_all.apk") keep=1 ;;
      latest-ipk.json|version) keep=1 ;;
      latest-apk.json)
        if jq -e --arg v "$RELEASE_VERSION" '.version == $v and .format == "apk"' "$file" >/dev/null 2>&1; then keep=1; fi
        ;;
    esac
    if [ "$keep" -eq 0 ] && [[ "$base" == luci-app-openkill* ]]; then
      git rm -f "$file" >/dev/null
      changed=1
      echo "removed package $base"
    fi
    if [ "$base" = latest-apk.json ] && [ "$keep" -eq 0 ]; then
      git rm -f "$file" >/dev/null
      changed=1
      echo "removed stale APK index"
    fi
  done < <(find master -maxdepth 1 -type f -print)
fi
if [ "$changed" -eq 1 ]; then
  git config user.name 'github-actions[bot]'
  git config user.email 'github-actions[bot]@users.noreply.github.com'
  git commit -m "Prune packages older than $RELEASE_VERSION"
  git push origin HEAD:package
fi
