"""DeepClean's Python implementation."""

__version__ = "0.9.18"


def main() -> None:
    from .cli import main as cli_main

    cli_main()
