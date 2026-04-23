"""SafeTrace command-line entry point.

Usage examples
--------------
    # Build the FAISS index from a folder of media:
    python main.py ingest path/to/video.mp4 path/to/img1.jpg

    # Run a query over the existing index:
    python main.py query "worker without helmet" --k 5

    # Launch the Streamlit UI (equivalent to `streamlit run frontend/app.py`):
    python main.py ui
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

from src.config import SETTINGS
from src.pipeline import SafeTracePipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)


def cmd_ingest(args: argparse.Namespace) -> int:
    pipe = SafeTracePipeline()
    frames = pipe.ingest(args.inputs, fps=args.fps)
    print(f"Indexed {len(frames)} frames into {SETTINGS.index_path}")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    pipe = SafeTracePipeline()
    results = pipe.analyze_query(args.query, k=args.k)
    out = json.dumps(results, indent=2)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(out)
    return 0


def cmd_ui(args: argparse.Namespace) -> int:
    app = Path(__file__).parent / "frontend" / "app.py"
    cmd = [
        sys.executable, "-m", "streamlit", "run", str(app),
        "--server.port", str(args.port),
        "--server.address", args.host,
        "--server.headless", "true",
    ]
    return subprocess.call(cmd)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="safetrace")
    sub = p.add_subparsers(dest="command", required=True)

    pi = sub.add_parser("ingest", help="Extract frames + build FAISS index")
    pi.add_argument("inputs", nargs="+", help="Video/image files")
    pi.add_argument("--fps", type=float, default=SETTINGS.frame_fps)
    pi.set_defaults(func=cmd_ingest)

    pq = sub.add_parser("query", help="Run analyze_query on the existing index")
    pq.add_argument("query")
    pq.add_argument("--k", type=int, default=SETTINGS.top_k)
    pq.add_argument("--output", "-o")
    pq.set_defaults(func=cmd_query)

    pu = sub.add_parser("ui", help="Launch the Streamlit UI")
    pu.add_argument("--host", default="0.0.0.0")
    pu.add_argument("--port", type=int, default=8501)
    pu.set_defaults(func=cmd_ui)

    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
