"""MacMaid - fast, safe macOS system cleanup and maintenance toolkit."""

__version__ = "0.14.9"


def main() -> None:
    from .cli import main as cli_main

    cli_main()
