#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 1 ]]; then
    NEW_VERSION="$1"
else
    YEAR=$(date +%Y)
    MONTH=$(date +%-m)
    PREFIX="v$YEAR.$MONTH."
    LAST=$(git tag --list "${PREFIX}*" | sed "s|${PREFIX}||" | sort -n | tail -1)
    RELEASE=$(( ${LAST:-0} + 1 ))
    NEW_VERSION="$YEAR.$MONTH.$RELEASE"
fi

# Guard: must be on main
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$BRANCH" != "main" ]]; then
    echo "Error: not on main (currently on '$BRANCH')."
    exit 1
fi

# Guard: clean working tree
if [[ -n "$(git status --porcelain)" ]]; then
    echo "Error: working tree is dirty. Commit or stash changes first."
    exit 1
fi

# Guard: tag must not already exist
if git rev-parse "v$NEW_VERSION" &>/dev/null; then
    echo "Error: tag v$NEW_VERSION already exists."
    exit 1
fi

echo "Releasing v$NEW_VERSION..."

uv version "$NEW_VERSION"
uv lock

git add pyproject.toml uv.lock
git commit -m "🚀 bump version to $NEW_VERSION"
git tag "v$NEW_VERSION"

git push
git push origin "v$NEW_VERSION"

echo "Done — v$NEW_VERSION pushed."