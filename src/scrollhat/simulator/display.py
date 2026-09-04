"""Terminal rendering of the simulated 17x7 matrix."""

import os
import shutil
import sys
import threading
import time
from collections import deque

from .i2c import WIDTH

# Ramp used when colour is unavailable; index 0 is reserved for an unlit LED.
_RAMP = " .:-=+*#%@"

_HIDE_CURSOR = "\x1b[?25l"
_SHOW_CURSOR = "\x1b[?25h"
_RESET = "\x1b[0m"
_DIM = "\x1b[38;2;90;90;90m"

# Colour of an unlit LED: the dark grey of the pHAT's solder mask, so the
# panel outline stays visible when the display is blank.
_OFF_RGB = (28, 28, 30)

# Grey a just-lit LED maps to, so the dimmest pixel still reads as "on".
_MIN_LIT = 45


def supports_color(stream):
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") in ("dumb", ""):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


class TerminalDisplay:
    """Draws the panel in place, repainting on every update.

    Anything the program prints is written *above* the panel: the writer hands
    log lines to `log()`, which erases the panel, emits the text, and redraws.
    """

    def __init__(self, stream=None, scale=2, color=None, status=True):
        self.stream = stream if stream is not None else sys.__stdout__
        self.scale = max(1, scale)
        self.color = supports_color(self.stream) if color is None else color
        self.status = status
        self.interactive = (
            bool(getattr(self.stream, "isatty", lambda: False)()) and self.color
        )
        # Set by install() when the keyboard buttons are wired up, so the
        # status line can show which of A/B/X/Y are down.
        self.buttons = None
        self._lines = []
        self._drawn = False
        self._pixels = None
        self._panel = None
        self._frame_times = deque(maxlen=30)
        # update(), log() and refresh() are called from the program thread,
        # whichever thread printed, and the key thread respectively.
        self._lock = threading.Lock()

    # -- painting ---------------------------------------------------------

    def update(self, panel):
        pixels = panel.pixels()
        with self._lock:
            # Only repaint when the visible matrix changes. The library flips
            # between two frames on every show(), so an idle 60 fps loop would
            # otherwise redraw an identical panel 60 times a second.
            if pixels == self._pixels:
                return
            self._pixels = pixels
            self._panel = panel

            self._frame_times.append(time.monotonic())
            self._lines = self._render(pixels, panel)

            if self.interactive:
                self._paint()
            else:
                self.stream.write("\n".join(self._lines) + "\n\n")
                self.stream.flush()

    def refresh(self):
        """Repaint the last frame, e.g. after a button changed state."""
        with self._lock:
            if self._panel is None or not self.interactive:
                return
            self._lines = self._render(self._pixels, self._panel)
            self._paint()

    def log(self, text):
        """Emit program output above the panel."""
        with self._lock:
            if not self.interactive:
                self.stream.write(text)
                self.stream.flush()
                return

            self._erase()
            self.stream.write(text)
            self._paint()

    def close(self):
        with self._lock:
            if self.interactive and self._drawn:
                self.stream.write(_SHOW_CURSOR)
                self.stream.flush()

    def _paint(self):
        if not self._lines:
            return
        out = []
        if self._drawn:
            out.append(f"\x1b[{len(self._lines)}A")
        else:
            out.append(_HIDE_CURSOR)
        for line in self._lines:
            out.append("\x1b[2K" + line + "\n")
        self.stream.write("".join(out))
        self.stream.flush()
        self._drawn = True

    def _erase(self):
        if not self._drawn or not self._lines:
            return
        # Move back to the top of the panel and clear to the end of screen.
        self.stream.write(f"\x1b[{len(self._lines)}A\x1b[0J")
        self._drawn = False

    # -- layout -----------------------------------------------------------

    def _render(self, pixels, panel):
        inner = WIDTH * self.scale
        lines = []

        if self.color:
            lines.append(_DIM + "╭" + "─" * inner + "╮" + _RESET)
            for row in pixels:
                cells = "".join(self._cell(value) for value in row)
                lines.append(_DIM + "│" + _RESET + cells + _RESET + _DIM + "│" + _RESET)
            lines.append(_DIM + "╰" + "─" * inner + "╯" + _RESET)
        else:
            lines.append("+" + "-" * inner + "+")
            for row in pixels:
                cells = "".join(self._ramp_char(value) * self.scale for value in row)
                lines.append("|" + cells + "|")
            lines.append("+" + "-" * inner + "+")

        if self.status:
            lines.append(self._status_line(panel))

        return lines

    def _ramp_char(self, value):
        if not value:
            return _RAMP[0]
        return _RAMP[1 + value * (len(_RAMP) - 2) // 256]

    def _cell(self, value):
        if value:
            # Lift lit pixels clear of the unlit background: a gamma-corrected
            # value of 5 is a faint but visible glow on the real panel, and
            # painting it as near-black would make it darker than "off".
            level = _MIN_LIT + round(value * (255 - _MIN_LIT) / 255)
            rgb = (level, level, level)
        else:
            rgb = _OFF_RGB
        return "\x1b[48;2;{};{};{}m".format(*rgb) + " " * self.scale

    def _status_line(self, panel):
        parts = ["asleep" if panel.asleep else f"frame {panel.displayed_frame}"]
        parts.append(f"{panel.updates} updates")
        fps = self._fps()
        if fps is not None:
            parts.append(f"{fps:.0f} fps")
        if self.buttons is not None and self.buttons.available:
            # Pressed keys are shown upper-case; the line stays plain text so
            # truncating it below cannot cut an escape sequence in half.
            pressed = self.buttons.pressed()
            parts.append(
                "keys "
                + " ".join(
                    label.upper() if label in pressed else label
                    for label in self.buttons.labels
                )
            )
        # Truncate rather than let the line wrap, which would throw off the
        # cursor arithmetic used to repaint in place.
        text = " · ".join(parts)[: shutil.get_terminal_size().columns - 1]
        return (_DIM + text + _RESET) if self.color else text

    def _fps(self):
        if len(self._frame_times) < 2:
            return None
        span = self._frame_times[-1] - self._frame_times[0]
        if span <= 0:
            return None
        return (len(self._frame_times) - 1) / span


class LineWriter:
    """Wraps a stream so whole lines are routed through the display."""

    def __init__(self, display, original):
        self._display = display
        self._original = original
        self._buffer = ""

    def write(self, text):
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._display.log(line + "\n")
        return len(text)

    def flush(self):
        if self._buffer:
            self._display.log(self._buffer)
            self._buffer = ""
        self._original.flush()

    def isatty(self):
        return self._original.isatty()

    def fileno(self):
        return self._original.fileno()

    def __getattr__(self, name):
        return getattr(self._original, name)
