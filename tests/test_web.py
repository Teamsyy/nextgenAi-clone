import re
from fastapi.testclient import TestClient
from app.web import create_app
from app.settings import Settings

def test_ui_creation_and_csrf(tmp_path):
    app = create_app(Settings(output_root=tmp_path, database_url=f"sqlite:///{tmp_path/'web.db'}"))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        home = client.get("/")
        assert home.status_code == 200
        token = re.search(r'name="csrf" value="([^"]+)"', home.text).group(1)
        assert client.post("/projects", data={"name":"bad"}).status_code == 403
        r = client.post("/projects",data={"csrf":token,"name":"UI","product_name":"Cup","source_url":"https://example.com","benefits":"","target_audience":"Adults","language":"th","tone":"friendly"})
        assert r.status_code == 200 and "Cup" in r.text
        assert "Manual review" in r.text
        assert client.get("/",headers={"host":"evil.example"}).status_code == 400
        assert client.post("/projects",headers={"origin":"https://evil.example"},data={"csrf":token}).status_code == 403
        r_origin = client.post("/projects",headers={"origin":"http://localhost"},data={"csrf":token,"name":"Loopback UI","product_name":"Cup","source_url":"https://example.com","benefits":"","target_audience":"Adults","language":"th","tone":"friendly"})
        assert r_origin.status_code == 200

