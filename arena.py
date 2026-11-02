#!/usr/bin/env python3
"""Local Agent Arena server launcher."""

from __future__ import annotations

import argparse

from config.server import serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="启动 Agent Arena 本地服务")
    parser.add_argument("--serve", action="store_true", help="启动本地网页（必需）")
    parser.add_argument("--port", type=int, default=7788, help="首选端口（默认 7788）")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args(argv)
    if not args.serve:
        parser.print_help()
        return 2
    return serve(port=args.port, open_browser=not args.no_open)


if __name__ == "__main__":
    raise SystemExit(main())
