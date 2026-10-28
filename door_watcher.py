"""Runs on the fridge hardware (e.g. a Raspberry Pi) and prints the same
ambient card the dashboard shows, using the same engine and database.

    python door_watcher.py                          # press Enter = door opens
    FROSTMIND_GPIO_PIN=17 python door_watcher.py    # real reed switch on GPIO17

Use the same FROSTMIND_DB for the dashboard so both read one database.
NOTE: the GPIO path is written for gpiozero but is UNTESTED on real hardware.
"""
import os

from db import FridgeDB
from engine import (ambient_text, build_ambient_card, meal_for_hour, now_ist,
                    schedule_day)


class SimulatedSensor:
    def wait_for_open(self):
        input("Press Enter to simulate the fridge door opening (Ctrl-C to quit) ")

    def wait_for_close(self):
        pass


class GPIOSensor:
    """Normally-open reed switch: the magnet closes it while the door is shut."""

    def __init__(self, pin: int):
        from gpiozero import Button  # imported lazily, only needed on the Pi
        self.switch = Button(pin, pull_up=True)

    def wait_for_open(self):
        self.switch.wait_for_release()

    def wait_for_close(self):
        self.switch.wait_for_press()


def get_sensor():
    pin = os.getenv("FROSTMIND_GPIO_PIN")
    return GPIOSensor(int(pin)) if pin else SimulatedSensor()


def main():
    db = FridgeDB(os.getenv("FROSTMIND_DB", "inventory.db"))
    sensor = get_sensor()
    try:
        while True:
            sensor.wait_for_open()
            now = now_ist()
            card = build_ambient_card(db, schedule_day(now), meal_for_hour(now.hour))
            print(ambient_text(card, now.strftime("%I:%M %p")))
            sensor.wait_for_close()
    except (KeyboardInterrupt, EOFError):
        print("\nFrostMind watcher stopped.")


if __name__ == "__main__":
    main()