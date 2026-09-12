"""Frames for the espresso machine display.

Every renderer here only *draws* into the scrollphathd buffer; the caller
calls `show()` once it has layered on whatever else the frame needs. Showing
from inside a renderer would push the unfinished frame to the panel as well,
and an overlay like `wipe()` would then flicker against it.
"""

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
# Seconds the power-on line takes to draw across, then to open vertically.
SCAN_SECONDS = 0.40
OPEN_SECONDS = 0.27
POWER_SECONDS = SCAN_SECONDS + OPEN_SECONDS

# As dark as a lit LED can go and still read as lit. The library gamma-corrects
# on the way out, so a linear 0.3 leaves only a twentieth of the light of a
# linear 1.0: anything that dips that low blinks off rather than dimming.
DIM = 0.55


def _wave(period: float, phase: float = 0.0) -> float:
    """A 0.0-1.0 sine riding on the clock, so animations need no state."""
    return 0.5 + 0.5 * math.sin(2 * math.pi * (time.monotonic() / period + phase))


def heating(value: int):
    # each column is 5°C
    # 17 columns in the matrix
    # shows values in range 15-100°C

    value = max(value, 15)
    value = min(value, 100)
    # 15-100C needs 18 columns at 5C each, one more than there is, so the top
    # of the range shares the last column rather than drawing off the panel.
    w = min((value - 10) // 5, WIDTH)

    # Draws one frame and returns, so a caller running a render loop stays
    # responsive; the animation comes from the clock rather than from sleeping.
    scrollphathd.clear()
    scrollphathd.fill(1.0, 0, 0, WIDTH, 1)
    scrollphathd.fill(1.0, 0, 1, w, HEIGHT - 2)
    scrollphathd.fill(1.0, 0, HEIGHT - 1, WIDTH, 1)
    _sheen(w)


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


def temperature(value: int, heating: bool = False, boost: bool = False):
    scrollphathd.clear()
    if value > 99:
        scrollphathd.write_string(f"{value}!")
    else:
        scrollphathd.write_string(f"{value:02d}°")
        if heating:
            # Breathes while the element is on.
            scrollphathd.fill(DIM + (1.0 - DIM) * _wave(BREATH_SECONDS), 12, 5, 2, 2)
        if boost:
            # Boost is the impatient one: a fast flicker instead of a breath.
            flicker = int(time.monotonic() / BOOST_FLICKER_SECONDS) % 2
            scrollphathd.fill(1.0 if flicker else DIM, 15, 5, 2, 2)


def shot(timer: int = 0):
    scrollphathd.clear()
    # The timer is 15 columns wide, which leaves the last one for the drip.
    scrollphathd.write_string(f":{timer:02d}")
    _drip(WIDTH - 1)


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


def power_on(progress: float):
    """Wake the display: a beam draws left to right, then opens vertically.

    A mask over whatever the caller drew, like `wipe()`, so the picture unfolds
    from the beam. Lighting every LED instead and cutting to the content at the
    end flashes the whole panel white. `progress` runs 0.0 to 1.0 over
    POWER_SECONDS; at 1.0 nothing is masked and the frame is the caller's own.
    """
    progress = min(max(progress, 0.0), 1.0)
    scan = SCAN_SECONDS / POWER_SECONDS
    middle = HEIGHT // 2

    if progress < scan:
        # None of the picture yet: just the beam drawing itself across.
        scrollphathd.clear()
        width = int(round(progress / scan * WIDTH))
        if width:
            scrollphathd.fill(1.0, 0, middle, width, 1)
        return

    # The two halves of the beam travel out past the edges, so the last frame
    # of the sweep is the picture with nothing left drawn over it.
    half = int(round((progress - scan) / (1.0 - scan) * (middle + 1)))
    top, bottom = middle - half, middle + half
    if top > 0:
        scrollphathd.clear_rect(0, 0, WIDTH, top)
    if bottom < HEIGHT - 1:
        scrollphathd.clear_rect(0, bottom + 1, WIDTH, HEIGHT - bottom - 1)
    for y in (top, bottom):
        if 0 <= y < HEIGHT:
            scrollphathd.fill(1.0, 0, y, WIDTH, 1)


def power_off(progress: float):
    """The same sweep run backwards, the way a CRT collapses to a line."""
    power_on(1.0 - progress)


def _demo(render, seconds: float, **kwargs):
    """Run one animated renderer at 60fps for a while."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        render(**kwargs)
        scrollphathd.show()
        time.sleep(1.0 / 60.0)


def _demo_power(render, under, **kwargs):
    """Run one power sweep at 60fps over the frame it reveals or collapses."""
    start = time.monotonic()
    progress = 0.0
    while progress < 1.0:
        progress = min((time.monotonic() - start) / POWER_SECONDS, 1.0)
        scrollphathd.clear()
        under(**kwargs)
        render(progress)
        scrollphathd.show()
        time.sleep(1.0 / 60.0)


if __name__ == "__main__":

    _demo_power(power_on, heating, value=90)
    _demo(heating, 10.0, value=90)
    _demo(temperature, 3.0, value=93, heating=True)
    _demo(ready, 3.0)
    for n in range(28):
        _demo(shot, 1.0, timer=n)
    _demo(temperature, 5.0, value=93, heating=True, boost=True)
    _demo_power(power_off, temperature, value=93, heating=True, boost=True)

    while True:
        time.sleep(10)
