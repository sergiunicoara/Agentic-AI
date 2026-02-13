from pathlib import Path

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

cv = DATA_DIR / "cv.md"
portfolio = DATA_DIR / "portfolio.md"

if not cv.exists():
    cv.write_text("# Sergiu CV\n\nPlaceholder CV content for RAG.", encoding="utf-8")

if not portfolio.exists():
    portfolio.write_text("# Sergiu Portfolio\n\nPlaceholder portfolio content for RAG.", encoding="utf-8")

print("Seed data written to data/cv.md and data/portfolio.md")
