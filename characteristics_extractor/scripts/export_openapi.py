"""Export the actual app schema without a running server, LM Studio or database."""

import argparse
import json
from pathlib import Path

from characteristics_extractor.app import create_app
from characteristics_extractor.repository import KtruRepository


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("openapi.json"))
    args = parser.parse_args()
    # Only construct a repository; generation never reads this path.
    schema = create_app(repository=KtruRepository("unused-for-openapi.db")).openapi()
    args.output.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output.resolve())
