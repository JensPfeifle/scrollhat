# scrollhat

Drives a [Pimoroni Scroll pHAT HD](https://shop.pimoroni.com/products/scroll-phat-hd)
on a Raspberry Pi as a status display for a Lelit Marax espresso machine.

The program subscribes to `marax/#` on an MQTT broker and renders the machine
state on the 17x7 matrix:

- `marax/machine` — status (`off` / `heating` / `ready`) and brew temperature,
  shown as a two-digit temperature plus a progress bar
- `marax/shot` — an active shot, shown as a running timer

The four Scroll pHAT HD buttons are wired up too: **A** publishes
`{"state": "off"}` and **B** publishes `{"state": "on"}` to `marax/control`.

## Requirements

- Raspberry Pi with a Scroll pHAT HD attached
- I2C enabled (`sudo raspi-config` → Interface Options → I2C)
- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- An MQTT broker reachable on the LAN

The broker address is currently hardcoded at the top of
`src/scrollhat/__init__.py` (`MQTT_HOST`, `MQTT_PORT`); edit it there if your
broker lives elsewhere.

## Development

Clone the repo and create the virtualenv:

```bash
git clone https://github.com/JensPfeifle/scrollhat.git
cd scrollhat
uv sync
```

`uv sync` installs the dev group as well (ruff, python-lsp-server) and pulls
`scrollphathd` from a Git fork pinned in `pyproject.toml`.

Run it in the foreground — Ctrl-C shuts down cleanly, blanking the display and
releasing the GPIO pins:

```bash
uv run scrollhat
```

Lint and format:

```bash
uv run ruff check .
uv run ruff format .
```

The `examples/` directory holds standalone scripts from the Pimoroni library
(scrolling text, fonts, button splash) plus `src/scrollhat/clock.py` and
`rdy.py`, which are scratch sketches for display layouts. Run them directly:

```bash
uv run python examples/example.py
```

Note that the hardware libraries (`scrollphathd`, `gpiozero`, `lgpio`) only
work on the Pi itself — there is no simulator, so develop against the real
device (e.g. over SSH).

## Installing the systemd service

`scrollhat.service` starts the display at boot and restarts it if the broker is
temporarily unreachable. It assumes the repo is checked out at
`/home/jens/git/scrollhat` and runs as user `jens`; adjust `User`, `Group`,
`WorkingDirectory` and `ExecStart` if yours differ.

The service runs the console script from the project virtualenv, so make sure
`uv sync` has been run first and `.venv/bin/scrollhat` exists.

Install and enable it:

```bash
sudo cp scrollhat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now scrollhat.service
```

Check that it came up:

```bash
systemctl status scrollhat.service
journalctl -u scrollhat.service -f
```

The unit adds the `gpio` and `i2c` supplementary groups so the service user can
reach `/dev/gpiochip*` and `/dev/i2c-1`. If it fails with a permission error,
confirm those groups exist and own the device nodes.

After editing the unit file, reinstall it with the same `cp` + `daemon-reload`,
then `sudo systemctl restart scrollhat.service`. Alternatively, symlink it
instead of copying so edits in the repo only need a `daemon-reload`:

```bash
sudo systemctl link /home/jens/git/scrollhat/scrollhat.service
```

To stop and disable:

```bash
sudo systemctl disable --now scrollhat.service
```
