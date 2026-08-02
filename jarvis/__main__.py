"""Entry point for ``python -m jarvis``."""

import asyncio
import sys


def main() -> None:
    """Start the Jarvis daemon."""
    from jarvis.runtime.daemon import JarvisDaemon

    daemon = JarvisDaemon()
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        print("\n⚡ Jarvis signing off.")
        sys.exit(0)


if __name__ == "__main__":
    main()
