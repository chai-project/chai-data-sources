# pylint: disable=line-too-long, missing-module-docstring

from dataclasses import dataclass
from enum import Enum, auto

from pendulum import DateTime


class DeviceType(Enum):
    """ The type of device. """
    THERMOSTAT = auto()
    VALVE = auto()


@dataclass
class DeviceTemperature:
    """ The device temperature indicated as the time it was measure, its value, and the device it applies to. """
    measured_at: DateTime
    value: float
    device: DeviceType
