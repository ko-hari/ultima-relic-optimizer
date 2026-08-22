from io import BytesIO

from web_app import app


def test_web_page_and_health_endpoint():
    client = app.test_client()
    page = client.get("/")
    health = client.get("/api/health")
    assert page.status_code == 200
    assert b"Board Command Console" in page.data
    assert health.status_code == 200
    assert health.get_json()["ok"] is True
    assert health.get_json()["max_monte_carlo_iterations"] >= 100


def test_web_page_exposes_clipboard_paste_support():
    client = app.test_client()
    page = client.get("/")
    script = client.get("/web/app.js")
    assert "Ctrl+V".encode() in page.data
    assert b'addEventListener("paste"' in script.data
    assert b"imageFileFromClipboard" in script.data


def test_png_upload_analysis():
    client = app.test_client()
    with open("Sample_Board.png", "rb") as sample:
        response = client.post(
            "/api/analyze",
            data={"image": (BytesIO(sample.read()), "clipboard.png")},
            content_type="multipart/form-data",
        )
    assert response.status_code == 200
    assert response.get_json()["source"] == "upload"


def test_sample_analysis_and_recommendation_flow():
    client = app.test_client()
    analyzed = client.post("/api/analyze")
    assert analyzed.status_code == 200
    board = analyzed.get_json()
    assert (board["width"], board["height"]) == (15, 15)
    assert len(board["states"]) == 225
    assert board["reward_count"] == 72
    assert board["inventory"] == {
        "Boom": 0,
        "Special Boom": 0,
        "Lazer X": 0,
        "Lazer Y": 0,
    }
    assert board["found_rewards"] == 23
    assert board["states"][8 * 15] == "reward_found"

    recommended = client.post("/api/recommend", json={
        "board": board,
        "inventory": {
            "Boom": 1,
            "Special Boom": 1,
            "Lazer X": 1,
            "Lazer Y": 1,
        },
        "objective": "balanced",
        "mode": "analytical",
        "iterations": 1000,
    })
    assert recommended.status_code == 200
    results = recommended.get_json()["recommendations"]
    assert 1 <= len(results) <= 5
    assert all(item["item"] not in {"Gunpowder Barrel", "Key"} for item in results)
    lazer_x_rows = [item["target_y"] for item in results if item["item"] == "Lazer X"]
    lazer_y_columns = [item["target_x"] for item in results if item["item"] == "Lazer Y"]
    assert len(lazer_x_rows) == len(set(lazer_x_rows))
    assert len(lazer_y_columns) == len(set(lazer_y_columns))
