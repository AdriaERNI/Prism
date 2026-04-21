"""Backward-compatible entry point — delegates to prism.__main__."""

from prism.__main__ import main

if __name__ == "__main__":
    main()
