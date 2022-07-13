# pylint: disable=line-too-long, missing-module-docstring

# The Efergy API, also known as the Energyhive API, is documented here: http://napi.hbcontent.com/document/index.php
# Note that the table on the right with the data types only describes what the data types are. You need to verify if,
# for a given endpoint, the argument accepts that particular datatype.
from __future__ import annotations

import logging
from dataclasses import dataclass
from time import sleep
from typing import List, Dict, Optional, Iterable, Any

import orjson as json
import requests
from dacite import Config, from_dict
from pendulum import DateTime

from chai_data_sources.current_power import CurrentPower
from chai_data_sources.exceptions import RequestException, EfergyConnectionError, EfergyServerError, EfergyJSONError, \
    EfergyUnknownError, EfergyInvalidTokenError, EfergyAPIAccessError, DaciteError, EfergyMultipleMetersError, \
    EfergyNoMeterReadingError, EfergyNoMeterError, EfergyDataclassError, EfergyInvalidTimestampError
from chai_data_sources.historic_power import HistoricPower
from chai_data_sources.utilities import optional, round_date, convert_timestamp_ms, \
    InvalidTimestampError, Minutes, timed_lru_cache

log = logging.getLogger(__name__)  # get a module-level logger
log.addHandler(logging.NullHandler())  # add a no-op handler that can be modified by other code using this package


@dataclass
class _PowerResult:
    sid: str
    data: List[Dict[DateTime, int]]
    units: str
    age: int


@dataclass
class _HistoryResult:
    sum: float
    duration: int
    units: str


class EfergyMeter:
    """ An instance to interact for you with the Efergy API and provide easy access to a meter. """
    def __init__(self, *, token: str, target: str = "http://www.energyhive.com/mobile_proxy"):
        """
        Link an Efergy meter to the data available from the Energyhive API.
        :param: token The app token to access the API.
                      A token can be created here: https://www.energyhive.com/settings/tokens .
        :param: target The target URL to access the Energyhive API. This URL should **not** contain a trailing / .
                       Can be changed to provide a mock server instead of a production server.
        """
        self.token = token
        self.target = target

    # MARK: calculated properties for easy access

    @property
    def current(self) -> CurrentPower:
        """ The current power reading in W. """
        return self.get_current()

    # MARK: support functions

    def _access_server(self, *, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        if not params:
            params = {}
        params["token"] = self.token
        try:
            response = requests.get(f"{self.target}{endpoint}", params=params)
            log.debug("accessing URL %s", response.request.url)
        except RequestException as exc:
            raise EfergyConnectionError(exc) from exc
        if response.status_code == 500:
            raise EfergyServerError
        if not response or not response.text:
            raise EfergyUnknownError(response.request.url)
        try:
            json_data = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise EfergyJSONError from exc
        return json_data

    @timed_lru_cache(seconds=6)
    def get_current(self) -> CurrentPower:
        """
        Retrieve the current power reading.
        :return: the current power reading for this Efergy meter.
        :raises:
            EfergyConnectionError: the server could not be accessed
            EfergyServerError: the server can be accessed, but returned a server error
            EfergyInvalidTokenError: the server can be accessed, but the token is invalid
            EfergyAPIAccessError: the server can be accessed, but returned another error
            EfergyNoMeterError: the server can be accessed and the token is valid, but there is no meter to read data
            EfergyMultipleMetersError: the server can be accessed and the token is valid, but there are multiple meters
            EfergyJSONError: the server can be accessed and the token is valid, but the API result is invalid JSON
            EfergyDataclassError: the server can be accessed and the token is valid, but the API result is invalid
            EfergyNoMeterReadingError: zero or ambiguous meter readings where returned instead of just one
            EfergyUnknownError: another unlisted error occurred
        >>> meter = EfergyMeter(token="Xlt_NrXGDTtyMuHLCYSpdF3P019VAGO-")
        >>> meter.get_current()
        CurrentPower(value=2223, expires=DateTime(2022, 5, 28, 7, 59, 0, tzinfo=Timezone('Europe/London')))
        """
        json_data = self._access_server(endpoint="/getCurrentValuesSummary")

        if not isinstance(json_data, List) or len(json_data) != 1:
            # we got an unexpected response, see if we can work out what is going on
            if isinstance(json_data, Dict):
                if optional(optional(json_data, "error", default={}), "id", 0) == 500:
                    raise EfergyServerError
                if optional(json_data, "status", default="") == "error":
                    # the error description uses multiple tags, try and find it
                    description = optional(json_data, 'desc', optional(json_data, 'description', '')).lower()
                    if description == "bad token":
                        raise EfergyInvalidTokenError
                    raise EfergyAPIAccessError(message=f"got server error: {description}")
                raise EfergyUnknownError(json_data)
            if len(json_data) == 0:
                raise EfergyNoMeterError
            if len(json_data) > 1:
                raise EfergyMultipleMetersError
            raise EfergyUnknownError(json_data)
        meter_data = json_data[0]
        try:
            data = from_dict(data_class=_PowerResult, data=meter_data,
                             config=Config({DateTime: convert_timestamp_ms}))
        except DaciteError as exc:
            raise EfergyDataclassError(exc) from exc
        except InvalidTimestampError as exc:
            raise EfergyInvalidTimestampError from exc

        power = data.data
        if len(power) != 1 or len(power[0]) != 1:
            raise EfergyNoMeterReadingError(power)

        reading = power[0]
        for key, value in reading.items():
            return CurrentPower(value, key.add(seconds=30))

    def get_historic(self, *, start: DateTime, end: DateTime, minutes: Minutes) -> Iterable[HistoricPower]:
        """
        Get the historic data entries for this meter for a given period and a given interval.
        The results are yielded, so you should use this function as if it is an iterator.
        *USE SPARINGLY* This function creates an API call for every interval. It is capped at 20 requests per second.
        :param start: The start of the period. Rounded down to the nearest minutes that are a multiple of `minutes`.
        :param end: The end of the period. Rounded up to the nearest minutes that are a multiple of `minutes`.
        :param minutes: The interval expressed as minutes.
        :return: Yields HistoricPower instances for every interval between the start and end date.
        """
        if end <= start:
            raise ValueError("the end date should be after the start date")

        # split the call into suitable intervals matching the number of minutes given as an argument

        # align the start and end to the minutes provided as argument
        start = round_date(start, minutes=minutes, round_down=True)
        end = round_date(end, minutes=minutes, round_down=False)

        minutes = minutes.value

        # create and execute all the separate calls
        current = start
        while current < end:
            # pylint: disable=loop-global-usage
            previous = current
            current = current.add(minutes=minutes)

            params = {
                "fromTime": previous.int_timestamp,
                "toTime": current.int_timestamp,
                "period": "custom",
                "offset": -60,  # TODO: does this offset need to be adjusted for DST?
            }

            json_data = self._access_server(endpoint="/getEnergy", params=params)

            try:  # pylint: disable=loop-try-except-usage
                data = from_dict(data_class=_HistoryResult, data=json_data, config=Config(cast=[int, float]))
            except DaciteError as exc:
                log.debug("unable to get the entry between %s and %s", previous.isoformat(), current.isoformat())
                raise EfergyDataclassError(exc) from exc

            assert data.duration == minutes * 60  # pylint: disable=loop-invariant-statement

            yield HistoricPower(data.sum, start=previous, end=current)
            sleep(1 / 20)  # pylint: disable=loop-invariant-statement


if __name__ == "__main__":
    pass
