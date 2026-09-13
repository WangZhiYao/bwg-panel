"""命令行入口：python -m app [--mock] [--host H] [--port P]"""

import argparse

import uvicorn

from app.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="搬瓦工面板后端")
    parser.add_argument("--mock", action="store_true", help="使用假 KiwiVM 数据离线演示")
    parser.add_argument("--host", default="127.0.0.1", help="默认 127.0.0.1（公网请走反代）")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    app = create_app(mock=args.mock, start_scheduler=True)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
