#!/usr/bin/env bash
set -euo pipefail

if [[ -t 1 ]]; then
  blue=$'\033[34m'
  green=$'\033[32m'
  red=$'\033[31m'
  reset=$'\033[0m'
else
  blue=""
  green=""
  red=""
  reset=""
fi

usage() {
  echo "Usage: ./release.sh <version>"
  echo
  echo "Example:"
  echo "  ./release.sh 0.2.0"
}

error() {
  echo "${red}ERROR:${reset} $*" >&2
}

step() {
  echo "${blue}==>${reset} $*"
}

success() {
  echo "${green}$*${reset}"
}

if [[ $# -ne 1 ]]; then
  usage >&2
  exit 1
fi

version="$1"
if [[ ! "$version" =~ ^[0-9]+[.][0-9]+[.][0-9]+$ ]]; then
  error "Version must use MAJOR.MINOR.PATCH format, such as 0.2.0."
  exit 1
fi

tag="v${version}"

status="$(git status --porcelain)"
if [[ -n "$status" ]]; then
  error "Working tree is not clean."
  echo "Commit or stash changes before releasing." >&2
  echo >&2
  echo "$status" >&2
  exit 1
fi

if git rev-parse --verify --quiet "refs/tags/${tag}" >/dev/null; then
  error "Tag ${tag} already exists."
  exit 1
fi

step "Running compile checks"
python3 -m compileall library_pipeline.py valuation tests

step "Running pytest"
.venv/bin/python -m pytest

step "Creating annotated tag ${tag}"
git tag -a "$tag" -m "Library Valuation ${tag}"

step "Pushing current branch"
git push

step "Pushing tag ${tag}"
git push origin "$tag"

success "========================================"
success "Release complete"
echo
success "Tag:"
echo "    ${tag}"
echo
success "Next step:"
echo "    Create a GitHub Release using CHANGELOG.md."
success "========================================"
