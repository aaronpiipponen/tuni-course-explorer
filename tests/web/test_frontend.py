"""Fixed built-frontend response boundary tests."""

from pathlib import Path

from fastapi.testclient import TestClient

from course_explorer_web.app import create_app


def test_frontend_serves_only_built_output(tmp_path: Path) -> None:
    """Serve the two shell URLs and assets without exposing source or HTML fallbacks."""
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<main>built shell</main>")
    (assets / "app.js").write_text("console.log('built asset')")
    client = TestClient(create_app(frontend_directory=dist))

    for path in ("/", "/docs"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.text == "<main>built shell</main>"
    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert asset.text == "console.log('built asset')"
    assert client.get("/api/not-a-feature").status_code == 404
    assert client.get("/src/course_explorer_web/app.py").status_code == 404
    assert client.get("/unknown/path").status_code == 404
