"""A fake smbus2 that decodes IS31FL3731 traffic back into a 17x7 frame.

`scrollphathd` talks to the Scroll pHAT HD through three smbus calls
(`write_byte_data`, `write_i2c_block_data`, `read_byte_data`). Everything the
display does is therefore visible as register writes, so emulating the chip's
register map is enough to recover exactly what the LEDs would show — including
gamma, global brightness, scroll, rotation and flips, since all of those are
applied by the library before the bytes reach us.
"""

# Register map, mirroring scrollphathd.is31fl3731.
_BANK_ADDRESS = 0xFD
_CONFIG_BANK = 0x0B

_FRAME_REGISTER = 0x01
_SHUTDOWN_REGISTER = 0x0A

_ENABLE_OFFSET = 0x00
_BLINK_OFFSET = 0x12
_COLOR_OFFSET = 0x24

_NUM_FRAMES = 8
_NUM_PIXELS = 144

WIDTH = 17
HEIGHT = 7


def _pixel_addr(x, y):
    """Translate an x,y coordinate to a pixel index (copied from scrollphathd)."""
    if x > 8:
        x = x - 8
        y = 6 - (y + 8)
    else:
        x = 8 - x

    return x * 16 + y


def _build_pixel_map():
    """Map chip pixel index -> (x, y), inverting what scrollphathd.show() does."""
    mapping = {}
    for x in range(WIDTH):
        for y in range(HEIGHT):
            mapping[_pixel_addr(x, HEIGHT - (y + 1))] = (x, y)
    return mapping


_PIXEL_MAP = _build_pixel_map()


class Panel:
    """The emulated IS31FL3731 plus the 17x7 matrix wired to it."""

    def __init__(self, on_show=None):
        self.on_show = on_show
        self.bank = 0
        self.displayed_frame = 0
        self.asleep = False
        self.updates = 0
        self._config = [0] * 256
        self._frames = [[0] * _NUM_PIXELS for _ in range(_NUM_FRAMES)]
        # The chip powers up with every LED disabled; scrollphathd.setup()
        # writes the enable pattern for the 17x7 matrix into each frame.
        self._enabled = [[0] * _NUM_PIXELS for _ in range(_NUM_FRAMES)]

    # -- register decoding ------------------------------------------------

    def write_byte(self, register, value):
        if register == _BANK_ADDRESS:
            self.bank = value
            return

        if self.bank == _CONFIG_BANK:
            self._config[register & 0xFF] = value
            if register == _FRAME_REGISTER:
                self.displayed_frame = value % _NUM_FRAMES
                self._show()
            elif register == _SHUTDOWN_REGISTER:
                # The register is active-low: 0 means shutdown.
                self.asleep = not value
            return

        self.write_block(register, [value])

    def write_block(self, register, values):
        if self.bank == _CONFIG_BANK:
            for offset, value in enumerate(values):
                self._config[(register + offset) & 0xFF] = value
            return

        frame = self.bank % _NUM_FRAMES

        if register >= _COLOR_OFFSET:
            target = self._frames[frame]
            start = register - _COLOR_OFFSET
        elif register >= _BLINK_OFFSET:
            return  # blink control, not simulated
        else:
            self._set_enabled(frame, register - _ENABLE_OFFSET, values)
            return

        for offset, value in enumerate(values):
            index = start + offset
            if 0 <= index < _NUM_PIXELS:
                target[index] = value & 0xFF

    def read_byte(self, register):
        if register == _BANK_ADDRESS:
            return self.bank
        if self.bank == _CONFIG_BANK:
            return self._config[register & 0xFF]
        return 0

    def _set_enabled(self, frame, start_byte, values):
        """Unpack the LED enable bitmap: one bit per pixel, LSB first."""
        enabled = self._enabled[frame]
        for offset, value in enumerate(values):
            base = (start_byte + offset) * 8
            for bit in range(8):
                index = base + bit
                if 0 <= index < _NUM_PIXELS:
                    enabled[index] = (value >> bit) & 1

    # -- readout ----------------------------------------------------------

    def pixels(self):
        """The visible matrix as HEIGHT rows of WIDTH values, each 0-255."""
        rows = [[0] * WIDTH for _ in range(HEIGHT)]

        if not self.asleep:
            frame = self._frames[self.displayed_frame]
            enabled = self._enabled[self.displayed_frame]
            for index, (x, y) in _PIXEL_MAP.items():
                if enabled[index]:
                    rows[y][x] = frame[index]

        return tuple(tuple(row) for row in rows)

    def _show(self):
        self.updates += 1
        if self.on_show is not None:
            self.on_show(self)


class SMBus:
    """Stand-in for `smbus2.SMBus`, backed by a shared `Panel`.

    The i2c address is ignored: there is only ever one simulated device, and
    accepting whatever address the caller passes keeps non-default wiring
    (0x75) working without extra configuration.
    """

    def __init__(self, bus=None, force=None):
        self.bus = bus
        self.panel = get_panel()

    def open(self, bus):
        self.bus = bus

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def write_byte_data(self, address, register, value):
        self.panel.write_byte(register, value)

    def write_i2c_block_data(self, address, register, data):
        self.panel.write_block(register, list(data))

    def read_byte_data(self, address, register):
        return self.panel.read_byte(register)


_panel = None


def get_panel():
    """The process-wide simulated panel, created on first use."""
    global _panel
    if _panel is None:
        _panel = Panel()
    return _panel
