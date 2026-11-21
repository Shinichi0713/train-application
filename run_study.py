"""学習支援アプリの起動スクリプト。

    python run_study.py
    → http://127.0.0.1:8000 をブラウザで開く
"""
import argparse

import uvicorn

from study_app.main import app


def main():
    parser = argparse.ArgumentParser(description="まなびサポート（算数・国語）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
