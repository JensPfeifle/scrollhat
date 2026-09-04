"""A terminal simulator for the Scroll pHAT HD's 17x7 white LED matrix.

`install()` puts a fake `smbus2` module into `sys.modules` before
`scrollphathd` imports it, so the unmodified library drives a simulated
IS31FL3731 whose frames are painted into the terminal:

    from scrollhat import simulator
    simulator.install()

    import scrollphathd
    scrollphathd.write_string("hello")
    scrollphathd.show()

Usually there is no need to call this by hand — run a script under the
simulator instead:

    uv run scrollhat-sim examples/example.py
"""

import atexit
import sys
import types

from .display import LineWriter, TerminalDisplay
from .i2c import HEIGHT, WIDTH, Panel, SMBus, get_panel
from .keys import KeyboardButtons

__all__ = [
    "HEIGHT",
    "WIDTH",
    "KeyboardButtons",
    "Panel",
    "TerminalDisplay",
    "install",
    "uninstall",
]

# The library imports smbus2; older forks import smbus. Claim both.
_MODULE_NAMES = ("smbus2", "smbus")

_installed = False
_display = None
_buttons = None
_saved_modules = {}
_saved_streams = {}


def install(
    scale=2, color=None, status=True, stream=None, capture_output=True, keyboard=True
):
    """Redirect Scroll pHAT HD output to the terminal.

    :param scale: terminal columns per LED (2 keeps pixels roughly square)
    :param color: force 24-bit colour on/off, default is to auto-detect
    :param status: show the frame/fps status line under the panel
    :param stream: where to draw, default is the real stdout
    :param capture_output: route the program's own prints above the panel
    :param keyboard: press the A/B/X/Y buttons with the a/b/x/y keys
    :returns: the :class:`~scrollhat.simulator.i2c.Panel` being simulated

    Must be called before `scrollphathd.setup()` (which happens on the first
    `show()`), otherwise the library has already grabbed the real i2c bus.
    """
    global _installed, _display, _buttons

    if _installed:
        return get_panel()

    scrollphathd = sys.modules.get("scrollphathd")
    if scrollphathd is not None and getattr(scrollphathd, "display", None) is not None:
        raise RuntimeError(
            "scrollphathd is already set up; install the simulator before the "
            "first call to scrollphathd.show()"
        )

    _display = TerminalDisplay(stream=stream, scale=scale, color=color, status=status)
    panel = get_panel()
    panel.on_show = _display.update

    for name in _MODULE_NAMES:
        _saved_modules[name] = sys.modules.get(name)
        module = types.ModuleType(name)
        module.SMBus = SMBus
        module.__doc__ = f"Simulated {name} provided by scrollhat.simulator."
        sys.modules[name] = module

    if keyboard:
        _buttons = KeyboardButtons(on_change=_display.refresh)
        if _buttons.start():
            _display.buttons = _buttons
        else:
            _buttons = None

    if capture_output:
        for name in ("stdout", "stderr"):
            original = getattr(sys, name)
            _saved_streams[name] = original
            setattr(sys, name, LineWriter(_display, original))

    atexit.register(uninstall)
    _installed = True
    return panel


def uninstall():
    """Undo :func:`install`, leaving the last frame on screen."""
    global _installed, _display, _buttons

    if not _installed:
        return

    if _buttons is not None:
        _buttons.stop()
        _buttons = None

    for name, original in _saved_streams.items():
        current = getattr(sys, name)
        if isinstance(current, LineWriter):
            current.flush()
            setattr(sys, name, original)
    _saved_streams.clear()

    for name, original in _saved_modules.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original
    _saved_modules.clear()

    if _display is not None:
        _display.close()
        _display = None

    get_panel().on_show = None
    _installed = False
