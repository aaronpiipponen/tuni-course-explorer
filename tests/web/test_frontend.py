"""Fixed built-frontend response boundary tests."""

from pathlib import Path

from fastapi.testclient import TestClient
from starlette.middleware.gzip import GZipMiddleware

from course_explorer_web.app import create_app


def test_frontend_serves_only_built_output(tmp_path: Path) -> None:
    """Serve the two shell URLs and assets without exposing source or HTML fallbacks."""
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    shell = "<main>built shell</main>" + "".join(f"<p>row {index}</p>" for index in range(80))
    (dist / "index.html").write_text(shell)
    (assets / "app.js").write_text("console.log('built asset')")
    application = create_app(frontend_directory=dist)
    client = TestClient(application)

    for path in ("/", "/docs"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.text == shell
    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert asset.text == "console.log('built asset')"
    assert client.get("/api/not-a-feature").status_code == 404
    assert client.get("/src/course_explorer_web/app.py").status_code == 404
    assert client.get("/unknown/path").status_code == 404

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
