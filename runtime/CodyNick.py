"""Classroom simulation transport; physical USB is not supported in this release."""
import json
from pathlib import Path


def event(kind, **values):
    print('@CODYNICK@' + json.dumps(dict(kind=kind, **values)), flush=True)


def inputs():
    try:
        return json.loads(Path('/workspace/input.json').read_text())
    except (OSError, ValueError):
        return {}


class Simulator:
    def __init__(self):
        print('[Simulator] Classroom workspace connected.', flush=True)

    def close(self):
        pass


class CN:
    def __init__(self):
        raise RuntimeError('Physical hardware is not enabled. Use CodyNick.Simulator().')


class RGB_Matrix:
    @staticmethod
    def set(cody, led, color):
        event('led', led=int(led), color=str(color))

    @staticmethod
    def clear(cody):
        event('clear_leds')


class Temperature_Sensor:
    @staticmethod
    def read(cody):
        return float(inputs().get('temperature', 21.5))


class Seven_Segment:
    @staticmethod
    def display(cody, value, *args, **kwargs):
        event('seven', value=str(value))


class LED_Matrix:
    @staticmethod
    def display_text(cody, text, speed='fast'):
        event('matrix', text=str(text), speed=str(speed))


class Joystick:
    @staticmethod
    def read(cody, *args):
        return inputs().get('joystick', 'neutral')
