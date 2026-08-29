from __future__ import annotations

import argparse
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from engine.effects import affected_positions
from engine.probability import Evaluation
from image_analysis import ImageBoard, ScreenshotAnalyzer
from models.board import Board
from models.cell import CellState
from models.item import ITEM_DEFINITIONS, MANUAL_ITEM_NAMES
from optimizer.exhaustive import exhaustive_recommendations
from optimizer.monte_carlo import monte_carlo_recommendations


DEFAULT_IMAGE = Path(__file__).with_name("Default.png")
OBJECTIVES = {
    "balanced": "균형형",
    "maximize_expected_rewards": "기대 보상",
    "maximize_explored_cells": "탐색 칸 수",
    "maximize_completion_probability": "완료 확률",
}


def format_target(evaluation: Evaluation) -> str:
    return "자동" if evaluation.target is None else f"({evaluation.target[0] + 1}, {evaluation.target[1] + 1})"


class OptimizerApp:
    def __init__(self, root: tk.Tk, image_path: Path | None = None):
        self.root = root
        self.root.title("Board Item Optimizer")
        self.root.geometry("1180x760")
        self.root.minsize(980, 650)
        self.image_board: ImageBoard | None = None
        self.results: list[Evaluation] = []
        self.preview = None
        self.original_overlay_var = tk.BooleanVar(value=True)
        self._build_ui()
        if image_path and image_path.exists():
            self.load_image(image_path)

    def _build_ui(self) -> None:
        self.root.configure(bg="#f4f1ea")
        header = tk.Frame(self.root, bg="#2b3440", height=54)
        header.pack(fill="x")
        tk.Label(header, text="BOARD ITEM OPTIMIZER", fg="#f6d37a", bg="#2b3440", font=("Segoe UI", 17, "bold")).pack(side="left", padx=20, pady=12)
        tk.Label(header, text="스크린샷 분석 · 기대값 기반 추천", fg="#cad2dd", bg="#2b3440", font=("Segoe UI", 10)).pack(side="left", padx=8, pady=14)

        body = tk.Frame(self.root, bg="#f4f1ea")
        body.pack(fill="both", expand=True, padx=14, pady=14)
        left = tk.Frame(body, bg="#fffdf8", bd=1, relief="solid", width=245)
        left.pack(side="left", fill="y", padx=(0, 12))
        left.pack_propagate(False)
        center = tk.Frame(body, bg="#252b32", bd=1, relief="solid")
        center.pack(side="left", fill="both", expand=True, padx=(0, 12))
        right = tk.Frame(body, bg="#fffdf8", bd=1, relief="solid", width=390)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        self._build_controls(left)
        self.canvas = tk.Canvas(center, bg="#252b32", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=12, pady=12)
        self.canvas.bind("<Configure>", lambda _event: self.render_board())
        self._build_results(right)

    def _build_controls(self, parent: tk.Frame) -> None:
        tk.Label(parent, text="입력 및 최적화", bg="#fffdf8", fg="#28323c", font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=16, pady=(18, 12))
        self.image_label = tk.Label(parent, text="이미지 미로드", bg="#eee9df", fg="#6b6b64", height=2, wraplength=200)
        self.image_label.pack(fill="x", padx=16, pady=(0, 8))
        ttk.Button(parent, text="스크린샷 열기", command=self.choose_image).pack(fill="x", padx=16, pady=4)

        section = tk.Frame(parent, bg="#fffdf8")
        section.pack(fill="x", padx=16, pady=(14, 0))
        self.reward_var = tk.IntVar(value=72)
        tk.Label(section, text="보드/보상", bg="#fffdf8", fg="#5e655f").grid(row=0, column=0, sticky="w")
        self.board_rule_label = tk.Label(section, text="자동 인식", bg="#fffdf8", fg="#3f6f54")
        self.board_rule_label.grid(row=0, column=1, sticky="e")
        tk.Label(section, text="목표 함수", bg="#fffdf8", fg="#5e655f").grid(row=1, column=0, sticky="w", pady=(9, 0))
        self.objective_var = tk.StringVar(value="balanced")
        ttk.Combobox(section, textvariable=self.objective_var, state="readonly", width=19, values=list(OBJECTIVES)).grid(row=1, column=1, sticky="e", pady=(9, 0))
        tk.Label(section, text="시뮬레이션 횟수", bg="#fffdf8", fg="#5e655f").grid(row=2, column=0, sticky="w", pady=(9, 0))
        self.iterations_var = tk.IntVar(value=1000)
        tk.Spinbox(section, from_=100, to=100000, increment=100, textvariable=self.iterations_var, width=8).grid(row=2, column=1, sticky="e", pady=(9, 0))

        tk.Label(parent, text="현재 아이템 수량", bg="#fffdf8", fg="#28323c", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=16, pady=(20, 8))
        self.inventory_vars: dict[str, tk.IntVar] = {}
        for item in MANUAL_ITEM_NAMES:
            row = tk.Frame(parent, bg="#fffdf8")
            row.pack(fill="x", padx=16, pady=2)
            tk.Label(row, text=item, bg="#fffdf8", fg="#5e655f", anchor="w").pack(side="left", fill="x", expand=True)
            var = tk.IntVar(value=0)
            self.inventory_vars[item] = var
            tk.Label(row, textvariable=var, bg="#eee9df", fg="#3f6f54", width=5).pack(side="right")

        ttk.Button(parent, text="추천 계산", command=self.analyze).pack(fill="x", padx=16, pady=(20, 5))
        ttk.Button(parent, text="샘플 이미지로 초기화", command=lambda: self.load_image(DEFAULT_IMAGE)).pack(fill="x", padx=16, pady=4)
        tk.Checkbutton(parent, text="원본 이미지에 추천 오버레이", variable=self.original_overlay_var, command=self.render_board, bg="#fffdf8", fg="#5e655f", activebackground="#fffdf8", selectcolor="#fffdf8").pack(anchor="w", padx=12, pady=(8, 0))
        tk.Label(parent, text="좌표는 1부터 시작합니다.\n보라/파랑 아이콘은 발견 보상,\n갈색 칸은 빈 칸, 석재 칸은 미확인으로 판정합니다.", bg="#fffdf8", fg="#82877f", justify="left", wraplength=205).pack(anchor="w", padx=16, pady=(18, 5))

    def _build_results(self, parent: tk.Frame) -> None:
        tk.Label(parent, text="추천 Top 5", bg="#fffdf8", fg="#28323c", font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=16, pady=(18, 2))
        self.status_label = tk.Label(parent, text="이미지를 분석하면 추천이 표시됩니다.", bg="#fffdf8", fg="#82877f", wraplength=350, justify="left")
        self.status_label.pack(anchor="w", padx=16, pady=(0, 10))
        columns = ("rank", "item", "target", "explored", "reward", "score")
        self.tree = ttk.Treeview(parent, columns=columns, show="headings", height=9)
        labels = {"rank": "#", "item": "아이템", "target": "표적", "explored": "탐색", "reward": "기대 보상", "score": "점수"}
        widths = {"rank": 28, "item": 105, "target": 55, "explored": 55, "reward": 65, "score": 55}
        for column in columns:
            self.tree.heading(column, text=labels[column])
            self.tree.column(column, width=widths[column], anchor="center")
        self.tree.pack(fill="x", padx=12)
        self.tree.bind("<<TreeviewSelect>>", self.show_reason)
        tk.Label(parent, text="추천 이유", bg="#fffdf8", fg="#28323c", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=16, pady=(18, 6))
        self.reason_text = tk.Text(parent, height=7, bg="#f4f1ea", fg="#4a514b", relief="flat", wrap="word", padx=8, pady=8)
        self.reason_text.pack(fill="x", padx=16)
        self.reason_text.configure(state="disabled")

    def choose_image(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg"), ("All files", "*.*")])
        if path:
            self.load_image(Path(path))

    def load_image(self, path: Path) -> None:
        try:
            self.image_board = ScreenshotAnalyzer().analyze(path)
            self.reward_var.set(self.image_board.board.reward_count)
            for item, quantity in self.image_board.inventory.items():
                if item in self.inventory_vars:
                    self.inventory_vars[item].set(quantity)
            size = self.image_board.board.width
            self.board_rule_label.configure(text=f"{size}×{size} / {self.image_board.board.reward_count}개")
            self.image_label.configure(text=path.name, fg="#3f6f54")
            self.status_label.configure(text=f"{size}×{size} 보드 분석 완료 · 발견 보상 {self.image_board.board.found_rewards}개 · 미확인 {self.image_board.board.unknown_count}칸")
            self.render_board()
        except Exception as exc:
            messagebox.showerror("이미지 분석 실패", str(exc))

    def current_board(self) -> Board:
        if self.image_board is not None:
            return self.image_board.board
        return Board.create(15)

    def inventory(self) -> dict[str, int]:
        return {name: var.get() for name, var in self.inventory_vars.items()}

    def analyze(self) -> None:
        try:
            board = self.current_board()
            inventory = self.inventory()
            # Analytical enumeration is instant and exact under the uniform
            # model; Monte Carlo can be selected explicitly from the CLI.
            self.results = exhaustive_recommendations(board, inventory, self.objective_var.get(), 5)
            self.tree.delete(*self.tree.get_children())
            for rank, result in enumerate(self.results, 1):
                self.tree.insert("", "end", iid=str(rank - 1), values=(rank, result.item, format_target(result), f"{result.expected_newly_explored_cells:.1f}", f"{result.expected_rewards:.2f}", f"{result.score:.3f}"))
            self.status_label.configure(text=f"{len(self.results)}개 후보를 평가했습니다. 점수는 {OBJECTIVES.get(self.objective_var.get(), self.objective_var.get())} 기준입니다.")
            self.render_board()
        except Exception as exc:
            messagebox.showerror("추천 계산 실패", str(exc))

    def show_reason(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected or not self.results:
            return
        result = self.results[int(selected[0])]
        self.reason_text.configure(state="normal")
        self.reason_text.delete("1.0", "end")
        self.reason_text.insert("1.0", f"{result.item} · 표적 {format_target(result)}\n\n{result.reason}\n\n보상 1개 이상 확률: {result.probability_of_at_least_one_reward:.1%}\n보드 완료 확률: {result.probability_of_completion:.1%}")
        self.reason_text.configure(state="disabled")
        self.render_board()

    def render_board(self) -> None:
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("all")
        board = self.current_board()
        pad = 12
        available_w = max(100, self.canvas.winfo_width() - 2 * pad)
        available_h = max(100, self.canvas.winfo_height() - 2 * pad)

        if self.image_board is not None and self.original_overlay_var.get():
            image = self.image_board.image.copy()
            scale = min(available_w / image.width, available_h / image.height)
            image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
            self.preview = ImageTk.PhotoImage(image)
            ox = (self.canvas.winfo_width() - image.width) / 2
            oy = (self.canvas.winfo_height() - image.height) / 2
            self.canvas.create_image(ox, oy, image=self.preview, anchor="nw")
            if self.results:
                result = self.results[0]
                region = self.image_board.region

                def image_rect(x: int, y: int) -> tuple[float, float, float, float]:
                    x0 = ox + (region.left + x * region.cell_width) * scale
                    y0 = oy + (region.top + y * region.cell_height) * scale
                    x1 = ox + (region.left + (x + 1) * region.cell_width) * scale
                    y1 = oy + (region.top + (y + 1) * region.cell_height) * scale
                    return x0, y0, x1, y1

                if result.target is not None:
                    try:
                        effect = affected_positions(board, result.item, result.target)
                    except ValueError:
                        effect = set()
                    for x, y in effect:
                        x0, y0, x1, y1 = image_rect(x, y)
                        self.canvas.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1, outline="#75e0db", width=1)
                    x0, y0, x1, y1 = image_rect(*result.target)
                    self.canvas.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1, outline="#ffe16b", width=3)
                    self.canvas.create_text((x0 + x1) / 2, max(oy + 10, y0 + 8), text="TOP", fill="#fff4ba", font=("Segoe UI", 9, "bold"))
                else:
                    x0, y0 = ox + region.left * scale, oy + region.top * scale
                    x1, y1 = ox + region.right * scale, oy + region.bottom * scale
                    self.canvas.create_rectangle(x0, y0, x1, y1, outline="#ffe16b", width=3)
                    self.canvas.create_text((x0 + x1) / 2, y0 + 10, text="TOP · AUTO", fill="#fff4ba", font=("Segoe UI", 9, "bold"))
            return

        size = min(available_w / board.width, available_h / board.height)
        ox = (self.canvas.winfo_width() - size * board.width) / 2
        oy = (self.canvas.winfo_height() - size * board.height) / 2
        colors = {CellState.UNKNOWN: "#cdb087", CellState.REWARD_FOUND: "#7258a4", CellState.NO_REWARD: "#76563f"}
        for cell in board.iter_cells():
            x0, y0 = ox + cell.x * size, oy + cell.y * size
            x1, y1 = x0 + size, y0 + size
            self.canvas.create_rectangle(x0, y0, x1, y1, fill=colors.get(cell.state, "#76563f"), outline="#4b3a2d", width=1)
            if cell.state is CellState.REWARD_FOUND:
                self.canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2, text="★", fill="#ffe48a", font=("Segoe UI", max(8, int(size * .42)), "bold"))
        if self.results:
            result = self.results[0]
            if result.target is not None:
                x, y = result.target
                x0, y0 = ox + x * size, oy + y * size
                x1, y1 = x0 + size, y0 + size
                self.canvas.create_rectangle(x0 + 2, y0 + 2, x1 - 2, y1 - 2, outline="#ffe16b", width=3)
                self.canvas.create_text((x0 + x1) / 2, y0 + 9, text="TOP", fill="#fff4ba", font=("Segoe UI", max(7, int(size * .2)), "bold"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Board Item Optimizer")
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE, help="board screenshot")
    parser.add_argument("--inventory", default="Boom=1,Special Boom=1,Lazer X=1,Lazer Y=1")
    parser.add_argument("--objective", choices=list(OBJECTIVES), default="balanced")
    parser.add_argument("--monte-carlo", type=int, default=0, metavar="N", help="validate with N simulations")
    parser.add_argument("--no-gui", action="store_true", help="print recommendations and exit")
    return parser


def parse_inventory(text: str) -> dict[str, int]:
    inventory = {name: 0 for name in MANUAL_ITEM_NAMES}
    for part in text.split(","):
        if not part.strip():
            continue
        name, quantity = part.split("=", 1)
        if name.strip() in inventory:
            inventory[name.strip()] = int(quantity)
    return inventory


def run_cli(args) -> int:
    analyzer = ScreenshotAnalyzer()
    image_board = analyzer.analyze(args.image) if args.image.exists() else None
    board = image_board.board if image_board else Board.create(15)
    inventory = image_board.inventory if image_board else parse_inventory(args.inventory)
    if args.monte_carlo:
        results = monte_carlo_recommendations(board, inventory, args.objective, 5, args.monte_carlo)
    else:
        results = exhaustive_recommendations(board, inventory, args.objective, 5)
    print(f"Board: {board.width}x{board.height}, found={board.found_rewards}, unknown={board.unknown_count}, remaining={board.remaining_rewards}")
    for rank, result in enumerate(results, 1):
        target = "auto" if result.target is None else f"({result.target[0] + 1},{result.target[1] + 1})"
        print(f"{rank}. {result.item:18} target={target:9} explored={result.expected_newly_explored_cells:6.2f} rewards={result.expected_rewards:6.3f} at_least_one={result.probability_of_at_least_one_reward:.2%} completion={result.probability_of_completion:.2%} score={result.score:.4f}")
        print(f"   {result.reason}")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.no_gui:
        return run_cli(args)
    root = tk.Tk()
    OptimizerApp(root, args.image if args.image.exists() else None)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
