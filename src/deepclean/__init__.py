"""DeepClean's Python implementation."""

__version__ = "0.9.22"


def main() -> None:
    from .cli import main as cli_main

    cli_main()
