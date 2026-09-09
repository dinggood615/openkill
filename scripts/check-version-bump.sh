#!/bin/sh
# Verify that a source version is strictly newer than the published version.
# Versions are YYYY-NNNN, where both components are compared numerically.
set -eu

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 SOURCE_VERSION RELEASED_VERSION" >&2
    exit 2
fi

source_version=$1
released_version=$2

is_version() {
    case "$1" in
        [0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9]) return 0 ;;
        *) return 1 ;;
    esac
}

decimal_component() {
    value=$1
    while [ "${value#0}" != "$value" ]; do
        value=${value#0}
    done
    [ -n "$value" ] || value=0
    printf '%s\n' "$value"
}

if ! is_version "$source_version"; then
    echo "Invalid source version: $source_version" >&2
    exit 2
fi
if ! is_version "$released_version"; then
    echo "Invalid released version: $released_version" >&2
    exit 2
fi

source_year=$(decimal_component "${source_version%-*}")
source_number=$(decimal_component "${source_version#*-}")
released_year=$(decimal_component "${released_version%-*}")
released_number=$(decimal_component "${released_version#*-}")

if [ "$source_year" -gt "$released_year" ] || \
   { [ "$source_year" -eq "$released_year" ] && [ "$source_number" -gt "$released_number" ]; }; then
    echo "Source version $source_version is greater than released version $released_version"
    exit 0
fi

echo "Source version $source_version must be greater than released version $released_version" >&2
exit 1
