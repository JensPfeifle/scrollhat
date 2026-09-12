import json
import signal
import time
from threading import Event

import paho.mqtt.client as mqtt
import scrollphathd
from gpiozero import Button

import rdy

MQTT_HOST = "10.0.1.178"
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60

machine_state = {
    "status": "off",
    "mode": "coffee",
    "brew_temp": 20,
    "steam_temp": 20,
    "heater": False,
    "boost": False,
}
shot_state = {"active": False, "timer": 0, "duration": 0}

# Set by SIGTERM/SIGINT so the render loop can unwind and blank the display.
stop = Event()


def on_connect(client, userdata, flags, reason_code, properties):
    print("Connected with result code " + str(reason_code))
    client.subscribe("marax/#")


def on_message(client, userdata, msg):
    global machine_state, shot_state
    print(f"{msg.topic} | {msg.payload.decode()}")
    if msg.topic == "marax/machine":
        payload = json.loads(msg.payload.decode())
        machine_state = payload

    if msg.topic == "marax/shot":
        payload = json.loads(msg.payload.decode())
        shot_state = payload


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

width, height = 17, 7

button_map = {
    5: ("A"),  # Top Left
    6: ("B"),  # Bottom Left
    16: ("X"),  # Top Right
    24: ("Y"),  # Buttom Right
}

state = "off"
temperature = 0.0
shot_start: time.time or None = None
shot_end: time.time or None = None

# How the brew temperature is drawn: "bar" is the progress-bar style, "value"
# spells the reading out. Button A swaps between them.
DISPLAY_MODES = ("bar", "value")
display_mode = DISPLAY_MODES[0]
# What a running shot puts on screen: its timer, or the brew temperature
# spelled out. Button A swaps between those while the shot lasts.
SHOT_VIEWS = ("timer", "temperature")
shot_view = SHOT_VIEWS[0]
# When the last swap happened, so the render loop can wipe the new view in.
# Starts one wipe in the past: nothing to sweep in before the first press.
mode_changed_at = -rdy.WIPE_SECONDS


def toggle_display_mode():
    global display_mode, mode_changed_at
    next_index = (DISPLAY_MODES.index(display_mode) + 1) % len(DISPLAY_MODES)
    display_mode = DISPLAY_MODES[next_index]
    mode_changed_at = time.monotonic()
    print(f"Display mode: {display_mode}")


def toggle_shot_view():
    global shot_view, mode_changed_at
    next_index = (SHOT_VIEWS.index(shot_view) + 1) % len(SHOT_VIEWS)
    shot_view = SHOT_VIEWS[next_index]
    mode_changed_at = time.monotonic()
    print(f"Shot view: {shot_view}")


def render_temperature():
    rdy.temperature(
        int(str(machine_state["brew_temp"])),
        heating=machine_state["heater"],
        boost=machine_state["boost"],
    )


def render_brew():
    if display_mode == "bar":
        rdy.heating(int(str(machine_state["brew_temp"])))
    else:
        render_temperature()


def pressed(button):
    button_name = button_map[button.pin.number]
    if button_name == "A":
        # A shot owns the display while it runs, so A swaps what it shows;
        # the rest of the time it swaps how the brew temperature is drawn.
        if shot_state["active"]:
            toggle_shot_view()
        else:
            toggle_display_mode()
    if button_name == "X":
        client.publish("marax/control", json.dumps({"state": "on"}))
    if button_name == "Y":
        client.publish("marax/control", json.dumps({"state": "off"}))


def render_shot():
    duration = shot_state["duration"]
    scrollphathd.write_string(f":{duration:02d}", x=1)


def request_stop(signum, frame):
    print(f"Received signal {signum}, shutting down")
    stop.set()


def main() -> None:
    global shot_view

    # systemd stops the unit with SIGTERM, so both signals have to unwind cleanly.
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    client.connect(MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE)
    # loop_start runs the network loop on a daemon thread, so a failure to stop
    # it cannot keep the process alive past shutdown.
    client.loop_start()

    scrollphathd.set_brightness(0.5)

    buttons = [Button(pin) for pin in button_map]
    for button in buttons:
        button.when_pressed = pressed

    # The display starts dark and sweeps on the first time the machine wakes.
    awake = False
    powered_at = -rdy.POWER_SECONDS
    shooting = False

    try:
        while not stop.is_set():
            scrollphathd.clear()
            if machine_state == {}:
                print("Waiting for machine state...")

            was_awake = awake
            awake = machine_state.get("status") in {"heating", "ready"}
            if awake != was_awake:
                powered_at = time.monotonic()

            power_progress = (time.monotonic() - powered_at) / rdy.POWER_SECONDS
            sweeping = power_progress < 1.0

            was_shooting = shooting
            shooting = shot_state["active"]
            if shooting and not was_shooting:
                # Every shot opens on its timer, whatever the last one ended on.
                shot_view = SHOT_VIEWS[0]

            # Whether something button A swaps is on screen, which is the only
            # time a swap is worth sweeping in.
            swappable = False

            if shooting and not sweeping:
                swappable = True
                if shot_view == "timer":
                    rdy.shot(timer=shot_state["timer"])
                else:
                    # The reading itself, never the bar: mid-shot the number is
                    # what is worth reading.
                    render_temperature()
            elif awake or sweeping:
                # Drawn during a sweep too, including the collapse of a machine
                # that has just gone off: the sweep masks the picture, so it
                # unfolds from the beam rather than flashing the panel white.
                swappable = True
                render_brew()
            # a machine that is off leaves the display blank

            if sweeping:
                # One overlay at a time: a mode swap mid-sweep arrives with it.
                if awake:
                    rdy.power_on(power_progress)
                else:
                    rdy.power_off(power_progress)
            elif swappable:
                progress = (time.monotonic() - mode_changed_at) / rdy.WIPE_SECONDS
                if progress < 1.0:
                    rdy.wipe(progress)

            scrollphathd.show()
            # Doubles as the frame delay and wakes immediately on a signal.
            stop.wait(1.0 / 60.0)
    finally:
        for button in buttons:
            button.close()
        client.loop_stop()
        client.disconnect()
        scrollphathd.clear()
        scrollphathd.show()


if __name__ == "__main__":
    main()
