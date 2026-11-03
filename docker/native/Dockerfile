# Build the native application libraries against an older glibc baseline, so the shared objects load
# on hosts whose glibc predates the build distribution's.
FROM oraclelinux:8 AS native-build

RUN dnf install -y --setopt=install_weak_deps=False gcc-c++ make libpq-devel \
    && dnf clean all

# The default builds the three serving libraries. The fixture library is an explicit test-only
# target that `scripts/build_native.py --fixtures` requests.
ARG NATIVE_TARGETS=all

COPY native /build
RUN make -C /build clean && make -C /build ${NATIVE_TARGETS}

FROM scratch AS output
COPY --from=native-build /build/*.so /
