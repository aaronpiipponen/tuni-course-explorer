# Wrapper around the pinned official multi-architecture llama.cpp server image.
#
# The base image provides the native CPU `llama-server` binary and the checksum
# tooling. This wrapper adds the fail-fast startup entrypoint that verifies the
# configured runtime revision and artifact checksum before the service can listen.
ARG EMBEDDING_SERVER_IMAGE
FROM ${EMBEDDING_SERVER_IMAGE}
ARG EMBEDDING_SERVER_IMAGE
# Compose expands EMBEDDING_SERVER_IMAGE in FROM without running the Python
# EmbeddingSettings validator, so this build layer enforces the same immutable
# digest pin on the build path. It performs format validation: the deployment
# value is config-owned in config/search.toml.
RUN set -eu; \
    fail() { printf '%s\n' "EMBEDDING_SERVER_IMAGE must be pinned by @sha256 digest" >&2; exit 1; }; \
    [ -n "${EMBEDDING_SERVER_IMAGE:-}" ] || fail; \
    image_repository="${EMBEDDING_SERVER_IMAGE%@sha256:*}"; \
    image_digest="${EMBEDDING_SERVER_IMAGE##*@sha256:}"; \
    case "$EMBEDDING_SERVER_IMAGE" in \
        *@sha256:*) ;; \
        *) fail ;; \
    esac; \
    case "$image_repository" in \
        ''|*@*|*[[:space:]]*) fail ;; \
    esac; \
    [ "${#image_digest}" -eq 64 ] || fail; \
    case "$image_digest" in \
        *[!0-9a-f]*) fail ;; \
    esac
ARG EMBEDDING_RUNTIME_REVISION
LABEL org.opencontainers.image.revision="${EMBEDDING_RUNTIME_REVISION}"
COPY --chmod=755 docker/embedding/entrypoint.sh /usr/local/bin/course-explorer-embedding-entrypoint
ENTRYPOINT ["/usr/local/bin/course-explorer-embedding-entrypoint"]
