"""Fixed built-frontend response boundary tests."""

import gzip
from pathlib import Path

from fastapi.testclient import TestClient
from starlette.middleware.gzip import GZipMiddleware

from course_explorer_web.app import create_app


def test_frontend_serves_shells_and_assets_with_cache_headers_and_precompressed_variants(
    tmp_path: Path,
) -> None:
    """Serve the shells and assets with their cache headers and precompressed variants."""
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    shell = "<main>built shell</main>" + "".join(f"<p>row {index}</p>" for index in range(80))
    (dist / "index.html").write_text(shell)
    script = "console.log('built asset')"
    (assets / "app.js").write_text(script)
    (assets / "app.js.gz").write_bytes(gzip.compress(script.encode()))
    (assets / "app.js.br").write_bytes(b"brotli-variant")
    application = create_app(frontend_directory=dist)
    client = TestClient(application)

    for path in ("/", "/docs", "/feedback"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.text == shell
        assert response.headers["cache-control"] == "no-cache"
    asset = client.get("/assets/app.js", headers={"Accept-Encoding": "identity"})
    assert asset.status_code == 200
    assert asset.text == script
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert "content-encoding" not in asset.headers
    assert client.get("/api/not-a-feature").status_code == 404
    assert client.get("/src/course_explorer_web/app.py").status_code == 404
    assert client.get("/unknown/path").status_code == 404

    # A precompressed gzip variant answers a request that admits gzip, and the decoded body stays
    # byte-identical to the built file.
    encoded = client.get("/assets/app.js", headers={"Accept-Encoding": "gzip"})
    assert encoded.status_code == 200
    assert encoded.headers["content-encoding"] == "gzip"
    assert encoded.headers["vary"] == "Accept-Encoding"
    assert encoded.content.decode("utf-8") == script
    with client.stream("GET", "/assets/app.js", headers={"Accept-Encoding": "br"}) as brotli:
        assert brotli.status_code == 200
        assert brotli.headers["content-encoding"] == "br"
        # The encoded variant keeps the plain file's content type.
        assert brotli.headers["content-type"] == asset.headers["content-type"]

    # The built shell crosses the gzip threshold: the serving boundary compresses it and the
    # decoded body stays byte-identical to the built file.
    compressed = client.get("/", headers={"Accept-Encoding": "gzip"})
    assert compressed.status_code == 200
    assert compressed.headers["content-encoding"] == "gzip"
    assert compressed.content.decode("utf-8") == shell

    # The installed compression layer carries the configured level and threshold.
    installed = [
        middleware for middleware in application.user_middleware if middleware.cls is GZipMiddleware
    ]
    assert len(installed) == 1
    assert installed[0].kwargs == {"minimum_size": 500, "compresslevel": 6}
