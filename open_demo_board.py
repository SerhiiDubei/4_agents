"""Open TIME WARS demo board (game model + timer on top) in default browser."""
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
board = ROOT / "game_modes" / "time_wars" / "demo_board.html"
if board.exists():
    webbrowser.open(board.as_uri())
    print("Відкрито:", board)
else:
    print("Файл не знайдено:", board)
