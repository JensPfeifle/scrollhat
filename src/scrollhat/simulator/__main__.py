"""Run a script or module against the simulated Scroll pHAT HD.

Usage:
    uv run scrollhat-sim examples/example.py
    uv run scrollhat-sim -m scrollhat
    uv run scrollhat-sim              # built-in demo
"""

import argparse
import os
import runpy
import sys

from . import install, uninstall


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="scrollhat-sim",
        description="Simulate the Scroll pHAT HD's 17x7 LED matrix in the terminal.",
    )
    parser.add_argument(
        "-m", "--module", help="run a module as __main__, e.g. scrollhat"
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=2,
        help="terminal columns per LED (default: 2)",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="ASCII output without colour, for logs and pipes",
    )
    parser.add_argument(
        "--no-status",
        action="store_true",
        help="hide the frame/fps line under the panel",
    )
    parser.add_argument(
        "--no-keys",
        action="store_true",
        help="do not read the keyboard for the A/B/X/Y buttons",
    )
    parser.add_argument(
        "--real-gpio",
        action="store_true",
        help="do not force gpiozero's mock pin factory",
    )
    parser.add_argument("script", nargs="?", help="path to a script to run")
    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="arguments passed on to the script or module",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    if args.module and args.script:
        print(
            "scrollhat-sim: give either -m MODULE or a script, not both",
            file=sys.stderr,
        )
        return 2

    if not args.real_gpio:
        # gpiozero has no pin factory off the Pi; its mock one lets the buttons
        # be constructed (they just never fire) so the app can run here.
        os.environ.setdefault("GPIOZERO_PIN_FACTORY", "mock")

    install(
        scale=args.scale,
        color=False if args.plain else None,
        status=not args.no_status,
        keyboard=not args.no_keys,
    )

    try:
        if args.module:
            sys.argv = [args.module] + args.args
            runpy.run_module(args.module, run_name="__main__", alter_sys=True)
        elif args.script:
            sys.argv = [args.script] + args.args
            sys.path.insert(0, os.path.dirname(os.path.abspath(args.script)))
            runpy.run_path(args.script, run_name="__main__")
        else:
            _demo()
    except KeyboardInterrupt:
        pass
    finally:
        uninstall()

    return 0


def _demo():
    """A short self-test: a brightness ramp, then some scrolling text."""
    import time

    import scrollphathd

    for step in range(18):
        scrollphathd.clear()
        for x in range(17):
            for y in range(7):
                scrollphathd.set_pixel(
                    x, y, min(1.0, max(0.0, (x + y + step) % 18 / 8.0))
                )
        scrollphathd.show()
        time.sleep(0.05)

    message = "SCROLL PHAT HD SIMULATOR "
    scrollphathd.clear()
    scrollphathd.set_brightness(0.6)
    length = scrollphathd.write_string(message)
    scrollphathd.show()

    for _ in range(length):
        scrollphathd.scroll(1)
        scrollphathd.show()
        time.sleep(0.06)


if __name__ == "__main__":
    sys.exit(main())
