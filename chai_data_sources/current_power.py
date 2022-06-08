# pylint: disable=line-too-long, missing-module-docstring

from dataclasses import dataclass

import pendulum


@dataclass
class CurrentPower:
    """ The current power use (in W) and when this value expires (aka when a new value becomes available). """
    value: int  # the current power reading in watt
    expires: pendulum.DateTime  # the expiry date of this value, with a new value available every 30 seconds
