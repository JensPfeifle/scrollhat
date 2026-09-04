"""Keyboard stand-ins for the four Scroll pHAT HD buttons.

The buttons hang off GPIO 5/6/16/24 and are read through gpiozero, so the
simulator drives them the same way the hardware does: it flips the matching
pin on gpiozero's mock pin factory, and any `Button` the program built sees a
real press. Holding a key down works too — terminal auto-repeat keeps
refreshing the release deadline.
"""

import os
import select
import sys
import termios
import threading
import time
import tty

try:
    from gpiozero.exc import GPIOZeroError as _GPIOZeroError
except ImportError:  # pragma: no cover - gpiozero is a hard dependency

    class _GPIOZeroError(Exception):
        pass


# Key -> BCM pin, matching the buttons on the board (A, B, X, Y).
DEFAULT_KEYMAP = (("a", 5), ("b", 6), ("x", 16), ("y", 24))

# How long a pin stays low after a keypress. Long enough for a program that
# polls `button.is_pressed` once a frame to see it, short enough that a tap
# does not read as a hold.
HOLD_SECONDS = 0.15

_POLL_SECONDS = 0.02


class KeyboardButtons:
    """Turns keypresses into gpiozero mock-pin edges on a background thread."""

    def __init__(self, keymap=DEFAULT_KEYMAP, hold=HOLD_SECONDS, on_change=None):
        self.keymap = dict(keymap)
        self.labels = [key for key, _ in keymap]
        self.hold = hold
        self.on_change = on_change
        self.available = False
        self._deadlines = {}
        self._stop = threading.Event()
        self._thread = None
        self._fd = -1
        self._saved_term = None

    def pressed(self):
        """Labels of the keys currently held down."""
        return set(self._deadlines)

    # -- lifecycle --------------------------------------------------------

    def start(self):
        stdin = sys.__stdin__
        if stdin is None or not stdin.isatty():
            return False

        try:
            self._fd = stdin.fileno()
            self._saved_term = termios.tcgetattr(self._fd)
            # cbreak rather than raw: ISIG stays on, so Ctrl-C still works.
            tty.setcbreak(self._fd)
        except (OSError, termios.error):
            self._fd = -1
            self._saved_term = None
            return False

        self.available = True
        self._thread = threading.Thread(
            target=self._run, name="scrollhat-keys", daemon=True
        )
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        for label in list(self._deadlines):
            self._release(label)
        if self._saved_term is not None:
            try:
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved_term)
            except (OSError, termios.error):
                pass
            self._saved_term = None
        self.available = False

    # -- input loop -------------------------------------------------------

    def _run(self):
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([self._fd], [], [], _POLL_SECONDS)
                if ready:
                    data = os.read(self._fd, 32)
                    for char in data.decode("utf-8", "ignore"):
                        self._press(char.lower())
            except (OSError, ValueError):
                break
            self._expire()

    def _press(self, label):
        pin = self.keymap.get(label)
        if pin is None:
            return

        new = label not in self._deadlines
        self._deadlines[label] = time.monotonic() + self.hold
        if new and self._drive(pin, low=True):
            self._changed()

    def _release(self, label):
        self._deadlines.pop(label, None)
        if self._drive(self.keymap[label], low=False):
            self._changed()

    def _expire(self):
        now = time.monotonic()
        for label, deadline in list(self._deadlines.items()):
            if deadline <= now:
                self._release(label)

    def _drive(self, pin_number, low):
        pin = _mock_pin(pin_number)
        if pin is None:
            return False
        try:
            if low:
                pin.drive_low()
            else:
                pin.drive_high()
        except (AssertionError, _GPIOZeroError):
            # A pin the program has closed or switched to output is not ours
            # to drive; that must not take the program down.
            return False
        return True

    def _changed(self):
        if self.on_change is not None:
            self.on_change()


def _mock_pin(pin_number):
    """The mock pin for a BCM number, or None if gpiozero is not mocked."""
    try:
        from gpiozero import Device

        Device.ensure_pin_factory()
        pin = Device.pin_factory.pin(pin_number)
    except (ImportError, _GPIOZeroError):
        return None

    # Anything but the mock factory is a real bus we have no business poking.
    return pin if hasattr(pin, "drive_low") else None
