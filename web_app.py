from __future__ import annotations

import argparse
import base64
from io import BytesIO
import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from PIL import Image

from engine.probability import Evaluation
from image_analysis import ImageBoard, ScreenshotAnalyzer, cv2
from models.board import Board
from models.cell import CellState
from models.item import MANUAL_ITEM_NAMES
from optimizer.exhaustive import exhaustive_recommendations
from optimizer.monte_carlo import monte_carlo_recommendations


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="/web")
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("BOARD_OPTIMIZER_MAX_UPLOAD_BYTES", str(8 * 1024 * 1024)))
MAX_MONTE_CARLO_ITERATIONS = max(100, int(os.getenv("BOARD_OPTIMIZER_MAX_MC_ITERATIONS", "100000")))


@app.errorhandler(ValueError)
def handle_value_error(error: ValueError):
    return jsonify({"error": str(error)}), 400


def image_data_url(image: Image.Image) -> str:
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def board_payload(image_board: ImageBoard) -> dict:
    board = image_board.board
    return {
        "width": board.width,
        "height": board.height,
        "reward_count": board.reward_count,
        "found_rewards": board.found_rewards,
        "remaining_rewards": board.remaining_rewards,
        "unknown_count": board.unknown_count,
        "states": [cell.state.value for cell in board.iter_cells()],
        "region": {
            "left": image_board.region.left,
            "top": image_board.region.top,
            "right": image_board.region.right,
            "bottom": image_board.region.bottom,
            "width": image_board.region.width,
            "height": image_board.region.height,
        },
        "image_data_url": image_data_url(image_board.image),
        "reward_centers": [[x, y] for x, y in image_board.reward_centers],
        "inventory": image_board.inventory,
        "detector": "opencv" if cv2 is not None else "pillow/numpy",
    }


def board_from_payload(payload: dict) -> Board:
    width = int(payload.get("width", 15))
    height = int(payload.get("height", width))
    if width != height:
        raise ValueError("Only square boards are supported")
    reward_count = payload.get("reward_count")
    board = Board.create(width, None if reward_count is None else int(reward_count))
    states = payload.get("states", [])
    if len(states) != width * height:
        raise ValueError("states must contain one value per cell")
    for cell, state in zip(board.iter_cells(), states):
        cell.state = CellState(state)
    return board


def evaluation_payload(evaluation: Evaluation) -> dict:
    result = evaluation.as_dict()
    result["target"] = None if evaluation.target is None else [evaluation.target[0], evaluation.target[1]]
    return result


@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/api/health")
def health():
    return jsonify({
        "ok": True,
        "opencv": cv2 is not None,
        "max_monte_carlo_iterations": MAX_MONTE_CARLO_ITERATIONS,
    })


@app.post("/api/analyze")
def analyze():
    upload = request.files.get("image")
    if upload and upload.filename:
        image = Image.open(upload.stream).convert("RGB")
        source = "upload"
    else:
        image = Image.open(BASE_DIR / "Sample_Board.png").convert("RGB")
        source = "sample"
    result = ScreenshotAnalyzer().analyze_image(image)
    response = board_payload(result)
    response["source"] = source
    return jsonify(response)


@app.post("/api/recommend")
def recommend():
    payload = request.get_json(force=True)
    board = board_from_payload(payload["board"])
    inventory = {name: max(0, int(payload.get("inventory", {}).get(name, 0))) for name in MANUAL_ITEM_NAMES}
    objective = payload.get("objective", "balanced")
    mode = payload.get("mode", "analytical")
    iterations = max(100, min(MAX_MONTE_CARLO_ITERATIONS, int(payload.get("iterations", 1000))))
    if mode == "monte_carlo":
        recommendations = monte_carlo_recommendations(board, inventory, objective, 5, iterations)
    else:
        recommendations = exhaustive_recommendations(board, inventory, objective, 5)
    return jsonify({
        "recommendations": [evaluation_payload(item) for item in recommendations],
        "mode": mode,
        "iterations": iterations if mode == "monte_carlo" else None,
    })


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Board Item Optimizer web GUI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=5000, type=int)
    return parser


if __name__ == "__main__":
    args = create_parser().parse_args()
    app.run(host=args.host, port=args.port, debug=False)
