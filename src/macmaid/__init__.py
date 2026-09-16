"""MacMaid's Python implementation."""

__version__ = "0.11.9"


def main() -> None:
    from .cli import main as cli_main

    cli_main()
