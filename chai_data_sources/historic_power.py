# pylint: disable=line-too-long, missing-module-docstring

from dataclasses import dataclass

import pendulum


@dataclass
class HistoricPower:
    """ The historic power use value (in kWh) for a given interval start-end. """
    value: float
    start: pendulum.DateTime
    end: pendulum.DateTime
