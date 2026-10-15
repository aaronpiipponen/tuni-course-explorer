#!/bin/sh
# Fail-fast startup wrapper for the pinned CPU-only BGE-M3 embedding service.
#
# The Compose runtime receives its configuration through the environment file that
# course_explorer_admin.compose generates from the owning settings. This entrypoint re-checks
# the exposure boundary, runtime identity, and artifact identity before the server can bind,
# then execs the pinned llama-server offline with fixed embedding semantics.
set -eu

fail() {
    printf '%s\n' "$1" >&2
    exit 1
}

: "${EMBEDDING_ARTIFACT_SHA256:?EMBEDDING_ARTIFACT_SHA256 is required}"
: "${EMBEDDING_RUNTIME_REVISION:?EMBEDDING_RUNTIME_REVISION is required}"
: "${EMBEDDING_MODEL:?EMBEDDING_MODEL is required}"
: "${EMBEDDING_HOST:?EMBEDDING_HOST is required}"
: "${EMBEDDING_PORT:?EMBEDDING_PORT is required}"
: "${EMBEDDING_THREADS:?EMBEDDING_THREADS is required}"
: "${EMBEDDING_CONTEXT_SIZE:?EMBEDDING_CONTEXT_SIZE is required}"
: "${EMBEDDING_POOLING:?EMBEDDING_POOLING is required}"
: "${EMBEDDING_NORMALIZATION:?EMBEDDING_NORMALIZATION is required}"

[ "$EMBEDDING_HOST" = "127.0.0.1" ] || fail "EMBEDDING_HOST must be 127.0.0.1"

case "$EMBEDDING_MODEL" in
    *[![:space:]]*) ;;
    *) fail "EMBEDDING_MODEL must not be blank" ;;
esac

case "$EMBEDDING_PORT" in
    '' | *[!0-9]*) fail "EMBEDDING_PORT must be decimal digits" ;;
esac
[ "$EMBEDDING_PORT" -ge 1 ] && [ "$EMBEDDING_PORT" -le 65535 ] ||
    fail "EMBEDDING_PORT must be between 1 and 65535"

case "$EMBEDDING_THREADS" in
    '' | *[!0-9]*) fail "EMBEDDING_THREADS must be decimal digits" ;;
esac
[ "$EMBEDDING_THREADS" -ge 1 ] || fail "EMBEDDING_THREADS must be at least 1"

case "$EMBEDDING_CONTEXT_SIZE" in
    '' | *[!0-9]*) fail "EMBEDDING_CONTEXT_SIZE must be decimal digits" ;;
esac
[ "$EMBEDDING_CONTEXT_SIZE" -ge 1 ] || fail "EMBEDDING_CONTEXT_SIZE must be at least 1"

case "$EMBEDDING_POOLING" in
    cls | mean | last) ;;
    *) fail "EMBEDDING_POOLING must be cls, mean, or last" ;;
esac

if [ "$EMBEDDING_NORMALIZATION" != "-1" ]; then
    case "$EMBEDDING_NORMALIZATION" in
        '' | *[!0-9]*) fail "EMBEDDING_NORMALIZATION must be -1 or a non-negative integer" ;;
    esac
fi

[ "${#EMBEDDING_ARTIFACT_SHA256}" -eq 64 ] ||
    fail "EMBEDDING_ARTIFACT_SHA256 must be 64 lowercase hexadecimal characters"
case "$EMBEDDING_ARTIFACT_SHA256" in
    *[!0-9a-f]*) fail "EMBEDDING_ARTIFACT_SHA256 must be 64 lowercase hexadecimal characters" ;;
esac

[ "${#EMBEDDING_RUNTIME_REVISION}" -eq 40 ] ||
    fail "EMBEDDING_RUNTIME_REVISION must be 40 lowercase hexadecimal characters"
case "$EMBEDDING_RUNTIME_REVISION" in
    *[!0-9a-f]*) fail "EMBEDDING_RUNTIME_REVISION must be 40 lowercase hexadecimal characters" ;;
esac

printf '%s  %s\n' "$EMBEDDING_ARTIFACT_SHA256" /models/embedding.gguf |
    /usr/bin/sha256sum --check --strict - ||
    fail "embedding artifact checksum mismatch"

if ! version_output="$(/app/llama-server --version 2>&1)"; then
    fail "llama-server --version failed"
fi
expected_prefix="$(printf '%.9s' "$EMBEDDING_RUNTIME_REVISION")"
case "$version_output" in
    *"commit ${expected_prefix})"*) ;;
    *) fail "llama-server runtime revision mismatch" ;;
esac

exec /app/llama-server \
    --model /models/embedding.gguf \
    --alias "$EMBEDDING_MODEL" \
    --host "$EMBEDDING_HOST" \
    --port "$EMBEDDING_PORT" \
    --threads "$EMBEDDING_THREADS" \
    --threads-batch "$EMBEDDING_THREADS" \
    --ctx-size "$EMBEDDING_CONTEXT_SIZE" \
    --batch-size "$EMBEDDING_CONTEXT_SIZE" \
    --ubatch-size "$EMBEDDING_CONTEXT_SIZE" \
    --pooling "$EMBEDDING_POOLING" \
    --embd-normalize "$EMBEDDING_NORMALIZATION" \
    --parallel 1 \
    --embedding \
    --device none \
    --offline \
    --poll 0 \
    --poll-batch 0 \
    --no-ui
