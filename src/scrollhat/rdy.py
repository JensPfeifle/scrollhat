import math
import time

import scrollphathd

scrollphathd.clear()
scrollphathd.set_brightness(0.5)


WIDTH, HEIGHT = 17, 7

# Seconds for the sheen to sweep the length of the heating bar.
SHEEN_SECONDS = 2.5
# Columns the sheen spreads either side of its centre.
SHEEN_SPREAD = 2.0
# Seconds for one breath of the heater dot.
BREATH_SECONDS = 1.6
# Seconds between flickers of the boost dot.
BOOST_FLICKER_SECONDS = 0.12
# Seconds for one glow cycle of the "RDY" text.
GLOW_SECONDS = 2.0
# Seconds for a drip to fall the height of the display.
DRIP_SECONDS = 1.4
# Seconds a mode-change wipe takes to cross the display.
WIPE_SECONDS = 0.35


def _wave(period: float, phase: float = 0.0) -> float:
    """A 0.0-1.0 sine riding on the clock, so animations need no state."""
    return 0.5 + 0.5 * math.sin(2 * math.pi * (time.monotonic() / period + phase))


def heating(value: int):
    # each column is 5°C
    # 17 columns in the matrix
    # shows values in range 15-100°C

    value = max(value, 15)
    value = min(value, 100)
    w = (value - 10) // 5

    # Draws one frame and returns, so a caller running a render loop stays
    # responsive; the animation comes from the clock rather than from sleeping.
    scrollphathd.clear()
    scrollphathd.fill(1.0, 0, 0, 17, 1)
    scrollphathd.fill(1.0, 0, 1, w, 5)
    scrollphathd.fill(1.0, 0, 6, 17, 1)
    _sheen(w)
    scrollphathd.show()


def _sheen(w: int):
    """A dip in brightness rolling along the bar, like heat moving through it."""
    # Starts and ends off the bar, so the sweep enters and leaves cleanly.
    travel = w + 2 * SHEEN_SPREAD
    centre = (time.monotonic() % SHEEN_SECONDS) / SHEEN_SECONDS * travel - SHEEN_SPREAD

    first = max(0, int(centre - SHEEN_SPREAD))
    last = min(w - 1, int(centre + SHEEN_SPREAD))
    for x in range(first, last + 1):
        falloff = 1.0 - abs(x - centre) / SHEEN_SPREAD
        if falloff <= 0:
            continue
        brightness = 1.0 - 0.4 * falloff
        for y in range(1, 6):
            scrollphathd.set_pixel(x, y, brightness)


def ready():
    scrollphathd.clear()
    # Glows gently rather than sitting there, so "ready" looks awake.
    scrollphathd.write_string("RDY", brightness=0.45 + 0.55 * _wave(GLOW_SECONDS))
    scrollphathd.show()


def temperature(value: int, heating: bool = False, boost: bool = False):
    scrollphathd.clear()
    if value > 99:
        scrollphathd.write_string(f"{value}!")
    else:
        scrollphathd.write_string(f"{value:02d}°")
        if heating:
            # Breathes while the element is on.
            scrollphathd.fill(0.3 + 0.7 * _wave(BREATH_SECONDS), 12, 5, 2, 2)
        if boost:
            # Boost is the impatient one: a fast flicker instead of a breath.
            flicker = int(time.monotonic() / BOOST_FLICKER_SECONDS) % 2
            scrollphathd.fill(1.0 if flicker else 0.35, 15, 5, 2, 2)
    scrollphathd.show()


def shot(timer: int = 0):
    scrollphathd.clear()
    # The timer is 15 columns wide, which leaves the last one for the drip.
    scrollphathd.write_string(f":{timer:02d}")
    _drip(WIDTH - 1)
    scrollphathd.show()


def _drip(x: int):
    """A drop falling down one column for as long as the shot runs."""
    fall = (time.monotonic() % DRIP_SECONDS) / DRIP_SECONDS * (HEIGHT + 1)
    head = int(fall)
    if head < HEIGHT:
        scrollphathd.set_pixel(x, head, 1.0)
    if 0 < head <= HEIGHT:
        # A faint tail, so a drop crossing the display at 60fps still reads.
        scrollphathd.set_pixel(x, head - 1, 0.5)


def wipe(progress: float):
    """Sweep the frame in from the left; `progress` runs 0.0 to 1.0.

    An overlay on whatever was just drawn, so it goes between the renderer
    and `show()` rather than showing anything itself.
    """
    edge = int(progress * (WIDTH + 1))
    if edge < WIDTH:
        scrollphathd.clear_rect(edge, 0, WIDTH - edge, HEIGHT)
        # A bright leading edge makes the sweep read as a curtain, not a glitch.
        scrollphathd.fill(1.0, edge, 0, 1, HEIGHT)


def _demo(render, seconds: float, **kwargs):
    """Run one animated renderer at 60fps for a while."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        render(**kwargs)
        time.sleep(1.0 / 60.0)


if __name__ == "__main__":

    _demo(heating, 10.0, value=90)
    _demo(temperature, 3.0, value=93, heating=True)
    _demo(ready, 3.0)
    for n in range(28):
        _demo(shot, 1.0, timer=n)
    _demo(temperature, 5.0, value=93, heating=True, boost=True)

    while True:
        time.sleep(10)
