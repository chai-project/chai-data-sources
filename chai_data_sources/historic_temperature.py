# pylint: disable=line-too-long, missing-module-docstring

from dataclasses import dataclass

import pendulum


@dataclass
class HistoricTemperature:
    """ The historic temperature value (in °C) for a given interval start-end. """
    value: float
    start: pendulum.DateTime
    end: pendulum.DateTime
