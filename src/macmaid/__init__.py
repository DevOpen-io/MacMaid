"""MacMaid - fast, safe macOS system cleanup and maintenance toolkit."""

__version__ = "0.13.4"


def main() -> None:
    from .cli import main as cli_main

    cli_main()
