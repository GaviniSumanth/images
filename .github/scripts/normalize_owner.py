#!/usr/bin/env python3
"""Write the normalized registry owner to the GitHub Actions output file."""

import os
import sys

from release_config import OWNER_PATTERN


def main() -> None:
    owner = os.environ.get("OWNER", "").strip().lower()
    if not OWNER_PATTERN.fullmatch(owner):
        print(f"::error::Invalid owner: {owner!r}")
        sys.exit(1)

    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(f"owner={owner}\n")
    else:
        print(f"owner={owner}")


if __name__ == "__main__":
    main()
