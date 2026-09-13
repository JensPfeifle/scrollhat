# Design prompt — scrollhat display redesign

A brief for Claude Design describing the hardware, the data we render, the
display states we draw today, and what the four buttons do. Use it as the
starting point for a redesigned UI.

## What the device is

scrollhat drives a **Pimoroni Scroll pHAT HD** on a Raspberry Pi as a status
display for a Lelit Marax espresso machine. It subscribes to `marax/#` on an
MQTT broker and paints the machine's state on the LED matrix. The four buttons
on the pHAT both change what the display shows and send commands back to the
machine.

## Display canvas and constraints

- **17 × 7 monochrome LED matrix.** No colour — each LED has one channel.
- **Per-pixel brightness** from `0.0` (off) to `1.0` (full). The library
  gamma-corrects on the way out, so brightness below roughly `0.3` linear
  reads as off rather than dim; `DIM ≈ 0.55` is treated as "as dark as a lit
  LED can go and still read as lit."
- **Global brightness** is set to `0.5`.
- Rendered at **~60 fps**. Every frame is `clear()` → draw → optional overlay
  → `show()`. All animation is derived from the wall clock (sine waves,
  modulo cycles), so frames are stateless — nothing sleeps inside a renderer.
- Because the panel is only 17 columns wide and 7 rows tall, everything must
  be legible at a glance: at most two digits of text, a symbol, and a few
  animated dots or bars. There is no room for words beyond a 3-glyph token
  like `RDY`.

## The data we render (application state)

Two MQTT topics feed two state dictionaries:

**`marax/machine`** → `machine_state`
- `status`: `"off"` | `"heating"` | `"ready"`
- `mode`: e.g. `"coffee"` (currently informational, not drawn)
- `brew_temp`: brew boiler temperature in °C (integer-ish)
- `steam_temp`: steam boiler temperature (currently not drawn)
- `heater`: bool — the heating element is actively on
- `boost`: bool — boost/PID overshoot mode is on

**`marax/shot`** → `shot_state`
- `active`: bool — a shot is currently being pulled
- `timer`: seconds elapsed in the running shot
- `duration`: final length of the last completed shot

Payloads arriving from the machine can be truncated or garbled; incomplete or
unparseable messages are dropped and the last good state is kept.

## Display states / frames we draw today

The main loop picks one of these each frame based on machine and shot state,
then layers a transition overlay on top when one is in progress.

1. **Off (blank).** When `status == "off"` and no shot is active, the panel is
   dark.

2. **Power-on sweep** (`power_on`, ~0.67 s). When the machine wakes
   (`status` becomes `heating`/`ready`), a bright horizontal beam draws left→
   right across the middle row, then opens vertically like a CRT powering on,
   revealing the content frame beneath it. Used as a *mask* over the real
   frame so the picture unfolds from the beam instead of flashing the panel
   white.

3. **Power-off sweep** (`power_off`). The same beam run in reverse — the
   picture collapses back to a line and goes dark. Drawn over the last frame
   as the machine goes off.

4. **Heating bar** (`heating`) — the default brew view. A progress bar for
   brew temperature: a top border row, a bottom border row, and a filled
   column block whose width maps temperature to columns at **5 °C per
   column**, covering the range **15–100 °C** across the 17 columns. A
   **sheen** (a dip in brightness) rolls along the bar every ~2.5 s, like heat
   moving through it.

5. **Temperature value** (`temperature`) — the alternate brew view, and the
   view used mid-shot. The reading spelled out as two digits plus a degree
   glyph (`93°`); over 99 °C it shows `NN!`. Two status dots in the
   bottom-right corner:
   - **Heater dot** — breathes (sine fade) while `heater` is on.
   - **Boost dot** — a fast flicker (instead of a breath) while `boost` is on.

6. **Shot timer** (`shot`) — while a shot is active. A running timer drawn as
   `:NN` across the first 15 columns, with a **drip** animation: a bright drop
   falling down the last column (with a faint tail) on a ~1.4 s loop, for as
   long as the shot runs.

7. **Shot temperature** — mid-shot alternate. Same as the temperature-value
   frame; lets you read the brew temperature during extraction instead of the
   timer.

8. **RDY glow** (`ready`) — a `RDY` token that glows gently (brightness
   oscillates on a ~2 s cycle) so "ready" looks awake. *Present as a renderer
   but not currently wired into the main loop.*

### Transitions / overlays

- **Mode-change wipe** (`wipe`, ~0.35 s). When a button-A toggle swaps what's
  on screen, a curtain with a bright leading edge sweeps in from the left to
  reveal the new view.
- **Power-on / power-off sweeps** double as transitions (see 2 and 3). Only
  one overlay runs at a time; a mode swap that lands during a sweep arrives
  with it.

## Buttons (as wired in code today)

The Scroll pHAT HD has four buttons, one per corner:

| Button | Position     | Action (current code)                                          |
|--------|--------------|----------------------------------------------------------------|
| **A**  | Top-left     | Context toggle. **During a shot:** swap timer ↔ temperature view. **Otherwise:** swap brew view between bar ↔ value. Each swap triggers the wipe transition. |
| **B**  | Bottom-left  | *No handler — currently unused.*                               |
| **X**  | Top-right    | Publish `{"state": "on"}` to `marax/control` (turn machine on). |
| **Y**  | Bottom-right | Publish `{"state": "off"}` to `marax/control` (turn machine off).|

> Note: the README currently documents A = off / B = on, but the code above is
> the actual behaviour. The redesign should settle this — decide the final
> button assignment and align both.

## What to design

Given the 17×7 monochrome canvas and the states above, propose a redesigned
UI. Consider:

- A coherent visual language across the off / heating / ready / shot states
  and their transitions.
- How to show brew temperature legibly — reconciling the bar view and the
  value view, or replacing them with something better for a 17-wide panel.
- How `heater` and `boost` status read at a glance.
- The shot experience (timer, drip, mid-shot temperature) and how a shot
  begins and ends visually.
- A clear, discoverable mapping for the four buttons (on / off / toggle /
  the unused B), and what feedback each press gives on-panel.
- Whether unused data (`steam_temp`, `mode`, `RDY`) should surface.

Keep every proposal within the hardware limits: 17×7, single channel,
per-pixel brightness 0.0–1.0 with gamma, ~60 fps, clock-driven animation.
