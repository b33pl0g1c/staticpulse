#!/bin/sh
set -e

# GitHub Actions mounts the repo owned by a different UID; let git trust it so
# `git diff` works inside the container.
git config --global --add safe.directory '*' 2>/dev/null || true

# When invoked as a GitHub Action, inputs arrive as INPUT_* env vars. Map the
# ones we care about onto the names the tool reads. (Harmless when running as a
# plain `docker run`, where these are unset.)
[ -n "$INPUT_GITHUB_TOKEN" ] && export GITHUB_TOKEN="$INPUT_GITHUB_TOKEN"
[ -n "$INPUT_GROQ_API_KEY" ] && export GROQ_API_KEY="$INPUT_GROQ_API_KEY"
[ -n "$INPUT_ARGS" ] && set -- $INPUT_ARGS

exec staticpulse "$@"
