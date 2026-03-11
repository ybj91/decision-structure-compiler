"""Entry point for standalone executable builds (PyInstaller).

This module is the target for PyInstaller's --name dsc build. It imports
and runs the Typer app directly, avoiding issues with console_scripts
entry points in frozen executables.
"""

from dsc.cli.main import app


def main():
    app()


if __name__ == "__main__":
    main()
