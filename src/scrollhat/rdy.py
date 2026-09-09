import scrollphathd
import time

scrollphathd.clear()
scrollphathd.set_brightness(0.5)


def heating(value: int):
    # each column is 5°C
    # 17 columns in the matrix
    # shows values in range 15-100°C

    value = max(value, 15)
    value = min(value, 100)
    w = (value - 10) // 5

    scrollphathd.clear()
    scrollphathd.fill(1.0, 0, 0, 17, 1)
    scrollphathd.fill(1.0, 0, 1, w, 5)
    scrollphathd.fill(1.0, 0, 6, 17, 1)
    for n in range(5):
        time.sleep(1)
        scrollphathd.fill(0, w, 1, 1, 5)
        scrollphathd.show()
        time.sleep(1)
        scrollphathd.fill(0.5, w, 1, 1, 5)
        scrollphathd.show()
    scrollphathd.show()


def ready():
    scrollphathd.clear()
    scrollphathd.write_string("RDY")
    scrollphathd.show()


def temperature(value: int, heating: bool = False, boost: bool = False):
    scrollphathd.clear()
    if value > 99:
        scrollphathd.write_string(f"{value}!")
    else:
        scrollphathd.write_string(f"{value:02d}°")
        if heating:
            scrollphathd.fill(1.0, 12, 5, 2, 2)
        if boost:
            scrollphathd.fill(1.0, 15, 5, 2, 2)
    scrollphathd.show()


def shot(timer: int = 0):
    scrollphathd.clear()
    scrollphathd.write_string(f":{timer:02d}")
    scrollphathd.show()


if __name__ == "__main__":

    heating(value=90)
    time.sleep(1.0)
    temperature(value=93, heating=True)
    time.sleep(1.0)
    ready()
    time.sleep(1.0)
    for n in range(28):
        shot(n)
        time.sleep(1.0)
    time.sleep(5.0)
    temperature(value=93, heating=True)

    while True:
        time.sleep(10)
