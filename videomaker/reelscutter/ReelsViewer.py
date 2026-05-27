import math
from pathlib import Path

from flask import Flask, render_template, request

from reelscutter.db import list_pipelines

TEMPLATES_DIR = Path(__file__).parent / "viewer_templates"

app = Flask(__name__, template_folder=str(TEMPLATES_DIR))

PER_PAGE = 20


@app.route("/")
def index():
    page = max(1, request.args.get("page", 1, type=int))
    records, total = list_pipelines(page=page, per_page=PER_PAGE)
    total_pages = math.ceil(total / PER_PAGE) if total else 1

    rows = [r.to_dict() for r in records]
    return render_template(
        "index.html",
        records=rows,
        page=page,
        total=total,
        total_pages=total_pages,
    )


def run(host: str = "127.0.0.1", port: int = 5051, debug: bool = False):
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run(debug=True)
