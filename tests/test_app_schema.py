from app.server import app, scene_schema


def test_web_app_exposes_the_shared_editor_schema():
    paths = {route.path for route in app.routes}
    assert "/api/schema" in paths
    result = scene_schema()
    assert "background" in result["scene"]
    assert "lighting" in result["scene"]
    assert "walk" in result["actions"]
    assert "props" in result and "materials" in result
