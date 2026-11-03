# Native libraries

Three serving C++ shared libraries, built in a container and loaded by Python, carry the fuzzy-name, recommendation and prerequisite work, and a fourth library serves the test fixtures.

## The three serving libraries

Each library serves one part of the request path, and each has its own Python loader module and its own format version.

| Library | Serves | Loader | Format version |
|---|---|---|---|
| `libcourse_lookup.so` | The token-coverage part of the fuzzy-name score, applied to the score array and positions the projection supplies | `src/course_explorer/search/native_lookup.py` | 1 |
| `libcourse_recommendation.so` | Recommendation relatedness, overlap, near-duplicate rejection and order | `src/course_explorer/recommendations/native_scorer.py` | 2 |
| `libcourse_prerequisite.so` | Prerequisite compilation, calculation identities, drawing projection, record view and evaluation | `src/course_explorer/prerequisite/native_compiler.py` | 5 |

The prerequisite library is compiled from `compiler.cpp`, `identity.cpp`, `projector.cpp`, `structure_view.cpp`, `writer.cpp`, `evaluator.cpp`, `api.cpp`, `library_api.cpp` and `pgloader.cpp`, with its headers beside them in `native/`. [Prerequisite compiler](/docs/backend/prerequisites/prerequisite-compiler.md#compiler-and-fact-loader) states what each of those units does.

[Native code](/docs/reference/glossary.md#serving-data) is the glossary term for this compiled form. The database extension that the packed exact search calls is built into the database image, as [Search](/docs/backend/search-and-discovery/search.md#the-packed-exact-read) describes.

## The fixture library

`libcourse_prerequisite_fixtures.so` materializes hand-built prerequisite record bundles for the prerequisite tests and the exporters that write the TypeScript solver fixtures. It compiles `fixture_reader.cpp`, `fixture_api.cpp`, `library_api.cpp`, `identity.cpp`, `projector.cpp`, `structure_view.cpp` and `writer.cpp`.

The library exposes `course_prerequisite_project_records` and the shared format version, error text, structure-record accessor and bundle release. Test support in `tests/prerequisite/_fixture_library.py` loads it through `src/course_explorer/native_library.py` and materializes the returned record view through `src/course_explorer/prerequisite/native_compiler.py`.

## The build

`scripts/build_native.py` builds the three serving libraries and copies the produced files into the `native/` directory of the checkout that contains the script. The destination comes from the script's own path, so a copy built with a shared virtual environment writes only into that copy.

```bash
./.venv/bin/python scripts/build_native.py
```

The `--fixtures` option adds the test-only fixture library to the same build and copies `libcourse_prerequisite_fixtures.so` beside the serving libraries.

```bash
./.venv/bin/python scripts/build_native.py --fixtures
```

The `--non-interactive` option passes `-n` to `sudo`, so a caller without a cached sudo credential fails instead of prompting.

```bash
./.venv/bin/python scripts/build_native.py --non-interactive
```

Without that option the script runs plain `sudo`, which may ask for a password. It then runs `sudo docker build --target output --build-arg NATIVE_TARGETS=<targets> --output type=local,dest=<temporary directory> -f docker/native/Dockerfile .`. The default target list is `all`, and `--fixtures` sets it to `all fixtures`. The build stage of `docker/native/Dockerfile` starts from `oraclelinux:8`, installs `gcc-c++`, `make` and `libpq-devel`, copies `native/` to `/build`, and runs `make clean` followed by `make` over the requested targets. A second stage copies the produced `.so` files to a scratch root, and the script reads them from the temporary output directory.

`native/Makefile` compiles with `-std=c++17 -O3 -ffp-contract=off -fPIC` and produces one shared object per target. The prerequisite target links `-lpq`, so its database loader resolves libpq symbols. Both targets compute their identity digests with the SHA-256 in `native/sha256.h`, so neither links a TLS library and a host needs no OpenSSL runtime.

The script copies every produced file into the target directory under a temporary name before it replaces any installed library, and it then replaces each installed library on its own. A build that produces no output raises `FileNotFoundError` naming the missing file, and every installed library stays as it was. A failure while replacing one library leaves the libraries replaced before it in place, so `native/` can hold a mix of the installed and the produced libraries until the command runs again.

## What the host provides

The compiled modules are loaded by the host's dynamic linker when a Python loader first calls them, so the host must provide two shared libraries of its own:

- `libpq`, which `libcourse_prerequisite.so` links for its per-worker database connection.
- `libstdc++`, the C++ standard library that all three serving libraries and the fixture library link for their own code.

The build image supplies the compiler, `make` and the development headers, so the host needs no toolchain and no header package. The identity digest comes from `native/sha256.h`, a SHA-256 written into the library, so the compiled modules load on a host whose OpenSSL is absent or of another major version. A host that lacks one of the two libraries fails the first read that loads the affected module, with the message that names `scripts/build_native.py`.

## Loading and version checks

`src/course_explorer/native_library.py` is the one loader. Its `load(path, version, configure, *, guidance)` maps a library once with `ctypes.CDLL` and holds the handle in one module mapping keyed by path, so the first call pays the load and every following call reuses it. A missing file, a library the linker cannot load, and a mismatched version each raise one `ValueError` that names the build command. The caller's `configure` callback declares the C signatures the library needs and returns its version function.

The guidance text is `./.venv/bin/python scripts/build_native.py` for a serving library and the same command with `--fixtures` for the fixture library. Each library module passes its own format version beside that callback.

A native call returns a negative count on failure, and the loader then raises the library's own thread-local message from `course_lookup_last_error`, `course_recommendation_last_error` or `course_prerequisite_last_error`.

`libcourse_prerequisite.so` holds one loaded fact bundle per open handle. `native_handle.py` owns that handle for one worker process: `worker_handle(settings)` builds the libpq connection string from the connection settings, opens one handle through `course_prerequisite_open`, and reuses it for as long as that connection string is the one it was opened from, and `close_database` closes it. The C entry points sit in `native/api.cpp` (`course_prerequisite_open`, `course_prerequisite_close`, `course_prerequisite_evaluate` and `course_prerequisite_compile_bundle`) and in `native/library_api.cpp` (the format version, error text, structure-record accessor and bundle release shared by both libraries). `native/pgloader.cpp` holds the database loader itself, with the fact collection and the connection handle it opens.

## Tests

The session fixture `native_serving_libraries` in `tests/conftest.py` fails the run with the build guidance when `libcourse_recommendation.so`, `libcourse_prerequisite.so` or `libcourse_lookup.so` is missing, and `tests/prerequisite/conftest.py` checks `libcourse_prerequisite_fixtures.so` the same way. `tests/native/test_native_library.py` proves that a missing prerequisite library fails `compile_direct_many` with `ValueError`, and that the same library loaded under another path with an increased `FORMAT_VERSION` fails with `ValueError` matching `mismatched format version`. No test builds a library, so the three serving objects and the fixture object exist before the suite runs.
