# pylint: disable=line-too-long, missing-module-docstring

# The Netatmo API is (incompletely) documented here: https://cbornet.github.io/netatmo-swagger-decl/
# For additional information on the OAuth2 process check out: https://dev.netatmo.com/apidocumentation/oauth
# The thermostatic valves are an API extension using "room" endpoints: https://dev.netatmo.com/apidocumentation/energy
#
# Netatmo uses a number of default names for device types. These are:
# NAPlug - relay
# NATherm1 - thermostat "cube"
# NRV - thermostatic valve

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict, TypeVar, Type, Tuple, Any

import dacite
import pendulum
import requests
from dacite import Config
from pendulum import DateTime, from_timestamp

from chai_data_sources.device_temperature import DeviceTemperature, DeviceType
from chai_data_sources.exceptions import NetatmoInvalidClientError, NetatmoInvalidTokenError, RequestException, \
    NetatmoConnectionError, NetatmoDataclassError, DaciteError, NetatmoJSONError, NetatmoUnknownError, \
    NetatmoThermostatError, NetatmoValveError, NetatmoRelayError, NetatmoMeasurementError, \
    NetatmoInvalidDurationError, NetatmoInvalidTemperatureError, NetatmoBoilerError
from chai_data_sources.historic_temperature import HistoricTemperature
from chai_data_sources.utilities import timed_lru_cache, Minutes, round_date

log = logging.getLogger(__name__)  # get a module-level logger

T = TypeVar("T")


class SetpointMode(Enum):
    """ Identify the preferred setpoint mode. """
    OFF = "off"
    MANUAL = "manual"  # manual temperature
    MAX = "max"
    # the next three modes are not supported by valves
    # PROGRAM = "program"  # preset program which defines when temperature changes
    # AWAY = "away"  # preset program when away which defines when temperature changes
    # HG = "hg"  # special protection mode to guard against frost


# MARK: API dataclass definitions

@dataclass
class _TokenRefreshResult:
    scope: List[str]
    access_token: str
    refresh_token: str
    expires_in: int
    expire_in: int


@dataclass
class _MeasurementData:
    # status: str
    # time_exec: float
    body: Dict[DateTime, List[float]]


@dataclass
class _HomesData:
    # status: str
    # time_exec: float
    # time_server: Optional[DateTime]
    body: _HomesDataBody
    # user: Optional[User]


@dataclass
class _HomesDataBody:
    homes: List[_Home]


@dataclass
class _Home:
    # pylint: disable=invalid-name,too-many-instance-attributes
    id: str
    name: str
    # altitude: int
    # coordinates: List[float]
    # country: str
    # timezone: str
    rooms: List[_Room]
    modules: List[_RoomModule]
    # therm_set_point_default_duration: Optional[int]
    # therm_boost_default_duration: Optional[int]
    # schedule: Optional[List[RoomSchedule]]
    therm_mode: str


@dataclass
class _RoomSchedule:
    # pylint: disable=invalid-name,too-many-instance-attributes
    name: str
    timetable: List[_TimeTableEntry]
    zones: List[_RoomZone]


@dataclass
class _RoomZone:
    # pylint: disable=invalid-name,too-many-instance-attributes
    name: str
    id: str
    type: int
    rooms: List[_RoomTherm]


@dataclass
class _RoomTherm:
    # pylint: disable=invalid-name,too-many-instance-attributes
    id: int
    therm_setpoint_temperature: float


@dataclass
class _RoomModule:
    # pylint: disable=invalid-name,too-many-instance-attributes
    id: str
    type: str
    # name: str
    # setup_date: DateTime
    # module_bridged: Optional[List[str]]


@dataclass
class _Room:
    # pylint: disable=invalid-name,too-many-instance-attributes
    id: str
    # name: str
    type: str
    module_ids: Optional[List[str]]


@dataclass
class _ThermostatsData:
    # pylint: disable=invalid-name,too-many-instance-attributes
    # status: str
    # time_exec: float
    # time_server: Optional[DateTime]
    body: _ThermostatsDataBody


@dataclass
class _User:
    # pylint: disable=invalid-name,too-many-instance-attributes
    email: str
    language: str
    locale: str
    feel_like_algorithm: int
    unit_pressure: int
    unit_system: int
    unit_wind: int
    id: str


@dataclass
class _ThermostatsDataBody:
    # pylint: disable=invalid-name,too-many-instance-attributes
    devices: List[_Device]


@dataclass
class _Device:
    # pylint: disable=invalid-name,too-many-instance-attributes
    _id: str
    type: str
    station_name: Optional[str]
    # firmware: int
    # plug_connected_boiler: bool
    # wifi_status: int
    modules: List[_Module]

    # place: Place
    # udp_conn: bool
    # last_setup: DateTime
    # last_status_store: DateTime
    # last_plug_seen: DateTime

    @property
    def id(self) -> str:
        """ Get the id associated with the device. """
        return self._id


@dataclass
class _Module:
    # pylint: disable=invalid-name,too-many-instance-attributes
    _id: str
    type: str
    # firmware: int
    # rf_status: int
    # battery_vp: int
    # therm_orientation: int
    # therm_relay_cmd: int
    # anticipating: bool
    # module_name: str
    battery_percent: int
    # last_therm_seen: DateTime
    setpoint: _SetPoint
    therm_program_list: List[_Program]
    measured: _Measurement

    @property
    def id(self) -> str:
        """ Get the id associated with the module. """
        return self._id


@dataclass
class _Measurement:
    # pylint: disable=invalid-name,too-many-instance-attributes
    time: DateTime
    temperature: float
    setpoint_temp: float


@dataclass
class _SetPoint:
    # pylint: disable=invalid-name,too-many-instance-attributes
    setpoint_mode: str


@dataclass
class _Program:
    # pylint: disable=invalid-name,too-many-instance-attributes
    program_id: str
    name: str
    selected: Optional[bool]
    timetable: List[_TimeTableEntry]
    zones: List[_Zone]


@dataclass
class _TimeTableEntry:
    # pylint: disable=invalid-name,too-many-instance-attributes
    id: int
    m_offset: int


@dataclass
class _Zone:
    # pylint: disable=invalid-name,too-many-instance-attributes
    name: Optional[str]
    id: int
    type: int
    temp: float


@dataclass
class _Place:
    # pylint: disable=invalid-name,too-many-instance-attributes
    altitude: int
    city: str
    continent: str
    country: str
    country_name: str
    location: List[float]
    street: str
    timezone: str


@dataclass
class _SetpointChange:
    # pylint: disable=invalid-name,too-many-instance-attributes
    status: str
    # time_exec: float
    # time_server: int


@dataclass
class _HomeStatus:
    status: str
    # time_server: int
    body: _HomeStatusBody


@dataclass
class _HomeStatusBody:
    home: _HomeStatusEntry


@dataclass
class _HomeStatusEntry:
    id: str
    rooms: List[_HomeStatusRoom]
    modules: List[_HomeStatusModule]


@dataclass
class _HomeStatusRoom:
    id: str
    reachable: bool
    anticipating: bool
    heating_power_request: int
    open_window: bool
    therm_measured_temperature: float
    therm_setpoint_temperature: float
    therm_setpoint_mode: str


@dataclass
class _HomeStatusModule:
    id: str
    type: str
    # firmware_revision: int
    # rf_strength: int
    # wifi_strength: Optional[int]
    boiler_status: Optional[bool]


# MARK: main Netatmo instance


class NetatmoClient:
    """ A client to interact for you with the Netatmo API and provide easy access to a thermostat and valve. """
    # pylint: disable=too-many-instance-attributes
    client_id: str
    client_secret: str
    refresh_token: str
    oauth: str
    target: str
    access_token: Optional[str] = None
    _relay_id: Optional[str] = None
    _thermostat_id: Optional[str] = None
    _home_id: Optional[str] = None
    _room_id: Optional[str] = None
    _valve_id: Optional[str] = None

    _thermostat_on: Optional[bool] = None
    _boiler_on: Optional[bool] = None
    _valve_on: Optional[bool] = None
    _valve_percentage: Optional[int] = None

    def __init__(self, *, client_id: str, client_secret: str, refresh_token: str,
                 oauth: str = "https://api.netatmo.com/oauth2",
                 target: str = "https://api.netatmo.com/api"):
        """
        Link a Netatmo token and a Netatmo app to the data available from the Netatmo API.
        :param client_id: The ID associated with the app that has permission to read and write to the thermostat.
        :param client_secret: The secret associated with the registered app.
        :param refresh_token: the refresh token associated with the thermostat account and the given authority.
        :param oauth: The target URL to access the Netatmo OAuth2 API. This URL should **not** contain a trailing / .
                      Can be changed to provide a mock server instead of a production server.
        :param target: The target URL to access the Netatmo API. This URL should **not** contain a trailing / .
                       Can be changed to provide a mock server instead of a production server.
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.oauth = oauth
        self.target = target

        log.debug("instance created with client ID: %s and secret: %s.", self.client_id, self.client_secret)

    # MARK: calculated properties for easy access

    @property
    def relay_id(self) -> str:
        """ The ID of the Netatmo relay. """
        if not self._relay_id:
            log.debug("relay information not set; retrieving ...")
            self._get_thermostat_data()
        return self._relay_id

    @property
    def thermostat_id(self) -> str:
        """ The ID of the Netatmo thermostat/cube. """
        if not self._thermostat_id:
            log.debug("thermostat information not set; retrieving ...")
            self._get_thermostat_data()
        return self._thermostat_id

    @property
    @timed_lru_cache(15)
    def thermostat_on(self) -> bool:
        """ The state of the Netatmo thermostat. """
        # always get the latest thermostat information
        self._get_thermostat_data()
        return self._thermostat_on

    @property
    def valve_id(self) -> str:
        """ The ID of the Netatmo thermostatic valve. """
        if not self._valve_id:
            log.debug("valve information not set; retrieving ...")
            self._get_home_data()
        return self._valve_id

    @property
    @timed_lru_cache(15)
    def boiler_on(self) -> bool:
        """ The state of the (simulated/assumed) boiler. """
        self._get_boiler_status()
        return self._boiler_on

    @property
    @timed_lru_cache(15)
    def valve_on(self) -> bool:
        """ The state of the Netatmo thermostatic valve. """
        self._get_boiler_status()
        return self._valve_on

    @property
    @timed_lru_cache(15)
    def valve_percentage(self) -> int:
        """ The percentage of the Netatmo thermostatic valve. """
        self._get_boiler_status()
        return self._valve_percentage

    @property
    def home_id(self) -> str:
        """ The ID of the home where the Netatmo thermostatic valve is installed. """
        if not self._home_id:
            log.debug("valve information not set; retrieving ...")
            self._get_home_data()
        return self._home_id

    @property
    def room_id(self) -> str:
        """ The ID of the room where the Netatmo thermostatic valve is installed. """
        if not self._room_id:
            log.debug("valve information not set; retrieving ...")
            self._get_home_data()
        return self._room_id

    @property
    def thermostat_temperature(self) -> float:
        """ The temperature reported by the Netatmo thermostat/cube. """
        return self.get_measurement(thermostat=True).value

    @property
    def valve_temperature(self) -> float:
        """ The temperature reported by the Netatmo thermostatic valve. """
        return self.get_measurement(thermostat=False).value

    # MARK: support functions

    def _renewal(self) -> None:
        """ Process the renewal of the token given a refresh token. """
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token
        }
        try:
            result = requests.post(f"{self.oauth}/token", data=payload)
            try:
                if result.status_code == 400 and json.loads(result.text) == {"error": "invalid_client"}:
                    raise NetatmoInvalidClientError
                if result.status_code == 400 and json.loads(result.text) == {"error": "invalid_grant"}:
                    raise NetatmoInvalidTokenError
            except json.decoder.JSONDecodeError:
                pass  # ignore JSON decode errors when dealing with 400 errors and raise the normal status error instead
            result.raise_for_status()
        except RequestException as exc:
            raise NetatmoConnectionError(exc) from exc
        try:
            json_result = result.json()
        except json.decoder.JSONDecodeError as exc:
            raise NetatmoJSONError from exc
        try:
            data: _TokenRefreshResult = dacite.from_dict(data_class=_TokenRefreshResult, data=json_result)
        except DaciteError as exc:
            raise NetatmoDataclassError(exc) from exc

        self.access_token = data.access_token
        self.refresh_token = data.refresh_token  # need to notify of changed refresh token?
        log.info("  access token renewed; the new access token is %s", self.access_token)

    def _access_server(self, *,
                       endpoint: str, payload: Optional[Dict[str, Any]] = None,
                       data_class=Type[T], config: Optional[Config] = None) -> T:
        url = f"{self.target}{endpoint}"
        if not payload:
            payload = {}
        payload["access_token"] = self.access_token if self.access_token else ""
        log.debug("accessing endpoint %s with payload %s", url, json.dumps(payload))
        try:
            response = requests.post(url, payload)
            if response.status_code == 403:  # our token may have expired
                log.debug("  an authentication error occurred; trying to renew the access token")
                self._renewal()  # try renewing it
                payload["access_token"] = self.access_token  # change to the new access token
                log.debug("  trying request again with access token %s", payload['access_token'])
                response = requests.post(url, payload)
            response.raise_for_status()
        except RequestException as exc:
            raise NetatmoConnectionError(exc) from exc
        if not response or not response.text:
            raise NetatmoUnknownError(response.request.url)
        try:
            json_data = response.json()
        except json.decoder.JSONDecodeError as exc:
            raise NetatmoJSONError from exc
        try:
            data: T = dacite.from_dict(data_class=data_class, data=json_data, config=config if config else Config())
        except DaciteError as exc:
            raise NetatmoDataclassError(exc) from exc
        return data

    def _get_thermostat_data(self):
        data: _ThermostatsData = self._access_server(endpoint="/getthermostatsdata",
                                                     data_class=_ThermostatsData,
                                                     config=Config({DateTime: from_timestamp}))

        if not data.body.devices or len(data.body.devices) > 1:
            raise NetatmoRelayError
        relay = data.body.devices[0]

        if not relay.modules or len(relay.modules) > 1:
            raise NetatmoThermostatError
        thermostat = relay.modules[0]

        self._relay_id = relay.id
        self._thermostat_id = thermostat.id
        self._thermostat_on = thermostat.measured.temperature < thermostat.measured.setpoint_temp

        log.info("identified the relay as %s and the thermostat as %s", self._relay_id, self._thermostat_id)

    def _get_home_data(self):
        data: _HomesData = self._access_server(endpoint="/homesdata", data_class=_HomesData,
                                               config=Config({DateTime: from_timestamp}))
        log.debug("Access to the thermostat data has been granted.")

        if len(data.body.homes) != 1:
            raise NetatmoValveError
        user_home = data.body.homes[0]
        self._home_id = user_home.id
        valves = [module for module in user_home.modules if module.type == "NRV"]
        if len(valves) != 1:
            raise NetatmoValveError
        self._valve_id = valves[0].id
        room = [room for room in user_home.rooms if self._valve_id in room.module_ids]
        if len(room) != 1:
            raise NetatmoValveError
        room = room[0]
        self._room_id = room.id

        log.info("identified the valve as %s", self._valve_id)

    def _get_boiler_status(self):
        data: _HomeStatus = self._access_server(endpoint="/homestatus", payload={"home_id": self._home_id},
                                                data_class=_HomeStatus, config=Config({DateTime: from_timestamp}))
        log.debug("Access to the boiler status has been granted.")

        home = data.body.home
        room = [room for room in home.rooms if self._room_id == room.id]
        boiler = [module for module in home.modules if module.type == "NATherm1"]
        if len(room) != 1:
            raise NetatmoBoilerError
        if len(boiler) != 1:
            raise NetatmoBoilerError
        room = room[0]
        boiler = boiler[0]
        if boiler.boiler_status is None:
            raise NetatmoBoilerError
        self._boiler_on = boiler.boiler_status
        self._valve_on = room.therm_setpoint_temperature > room.therm_measured_temperature
        self._valve_percentage = room.heating_power_request

    # MARK: public functions

    @timed_lru_cache(seconds=4 * 60)
    def get_measurement(self, *, thermostat: bool = True) -> DeviceTemperature:
        """
        Retrieve the current temperature of either the thermostat or the thermostatic valve.
        :param thermostat: get the temperature from the thermostat when True, or from the thermostatic valve otherwise
        :return: return when the temperature was measured, the temperature, and the device the temperature applies to
        """
        payload = {
            "device_id": self.relay_id,
            "module_id": self.thermostat_id if thermostat else self.valve_id,
            "scale": "max",
            "type": "Temperature",
            "limit": 1,
            "date_end": "last",
            "optimize": False,
        }

        data: _MeasurementData = self._access_server(endpoint="/getmeasure", payload=payload,
                                                     data_class=_MeasurementData,
                                                     config=Config({DateTime: lambda x: from_timestamp(int(x))}))

        if len(data.body) != 1:
            raise NetatmoMeasurementError
        measured_at, values = next(iter(data.body.items()), None)
        if len(values) != 1:
            raise NetatmoMeasurementError

        return DeviceTemperature(measured_at, values[0], DeviceType.THERMOSTAT if thermostat else DeviceType.VALVE)

    def get_historic(self, *, thermostat: bool = True,
                     start: DateTime, end: DateTime, minutes: Minutes) -> List[HistoricTemperature]:
        """
        Get the historic temperature entries for the thermostat or valve for a given period and a given interval.
        The algorithm maps forward initial unkown temperature values, and assumes no change in value between readings.
        As such, a response from the API such as --4---7---3-- would give a results 4444447777333 .
        :param thermostat: Retrieve the thermostat values when True, or the valve values when False.
        :param start: The start of the period. Rounded down to the nearest minutes that are a multiple of `minutes`.
        :param end: The end of the period. Rounded up to the nearest minutes that are a multiple of `minutes`.
        :param minutes: The interval expressed as minutes.
        :return: A list of HistoricTemperature instances for every interval between the start and end date.
        """
        # pylint: disable=too-many-locals
        if end <= start:
            raise ValueError("the end date should be after the start date")

        # align the start and end to the minutes provided as argument
        start = round_date(start, minutes=minutes, round_down=True)
        end = round_date(end, minutes=minutes, round_down=False)

        # the API itself has 30 minutes as the smallest binning; also align to those values
        start_30 = round_date(start, minutes=Minutes.MIN_30, round_down=True)
        end_30 = round_date(end, minutes=Minutes.MIN_30, round_down=False)

        # determine the number of intervals that we get from the API – we can request 21 days in one go
        duration = (end_30 - start_30).in_minutes()
        expected_intervals = duration / 30

        # split up the request into appropriately sized calls to the API
        intervals: List[Tuple[DateTime, DateTime]] = []

        while expected_intervals > 1024:
            custom_end_30 = start_30.add(minutes=1024 * 30)
            intervals.append((start_30, custom_end_30))
            start_30 = custom_end_30
            expected_intervals -= 1024

        assert (end_30 - start_30).in_minutes() / 30 == expected_intervals
        intervals.append((start_30, end_30))

        config = Config({DateTime: lambda x: from_timestamp(int(x))})
        entries: List[Tuple[DateTime, float]] = []
        for date_begin, date_end in intervals:
            payload = {
                "device_id": self.relay_id,
                "module_id": self.thermostat_id if thermostat else self.valve_id,
                "scale": "30min",
                "type": "Temperature",
                "limit": 1024,  # beware, only a maximum of 1024 records can be retrieved in one go
                "date_begin": date_begin.int_timestamp,
                "date_end": date_end.int_timestamp,
                "optimize": False,
            }

            data: _MeasurementData = self._access_server(endpoint="/getmeasure", payload=payload,
                                                         data_class=_MeasurementData,
                                                         config=config)

            for datetime in sorted(data.body.keys()):
                values = data.body[datetime]
                if len(values) != 1:
                    raise NetatmoMeasurementError
                entries.append((datetime, values[0]))

        # all entries from the API are stored in `entries` as pairs sorted by DateTime with one (1) temperature value
        if len(entries) < 1:
            raise NetatmoMeasurementError

        response: List[HistoricTemperature] = []
        _, previous_temperature = entries[0]

        current = start
        entries.reverse()  # change the order of the list to make removal (at the end) more efficient

        while current < end:
            current_end = current.add(minutes=minutes.value)
            if entries:
                entry_date, _ = entries[-1]  # pylint: disable=loop-invariant-statement
                while entry_date < current_end:  # find the entry that applies to this slot
                    entry_date, previous_temperature = entries.pop()
            response.append(HistoricTemperature(previous_temperature, current, current_end))
            current = current_end

        assert len(response) == (end - start).in_minutes() / minutes.value
        return response

    def turn_on_device(self, device: DeviceType, *, minutes: Optional[int] = 24 * 60) -> bool:
        """
        Turn the given device on. By default, this is in effect for a full day (24 hours).
        :param device: The device to turn on.
        :param minutes: The number of minutes to turn the device on before reverting to its previous setting.
        :return: True if the API reported success, False otherwise.
        """
        return self.set_device(device=device, mode=SetpointMode.MANUAL, temperature=30, minutes=minutes)

    def turn_off_device(self, device: DeviceType, *, minutes: Optional[int] = 24 * 60) -> bool:
        """
        Turn the given device off. For a valve, by default, this is in effect for a full day (24 hours).
        :param device: The device to turn off.
        :param minutes: The number of minutes to turn the device on before reverting to its previous setting.
                        Providing the minutes only has an effect when the device is a valve.
        :return: True if the API reported success, False otherwise.
        """
        if device == DeviceType.THERMOSTAT:
            return self.set_device(device=device, mode=SetpointMode.OFF)
        return self.set_device(device=device, mode=SetpointMode.MANUAL, temperature=7, minutes=minutes)

    def set_device(self, *, device: DeviceType, mode: SetpointMode = SetpointMode.MANUAL,
                   temperature: Optional[int] = None, minutes: Optional[int] = None) -> bool:
        """
        Set a given device to a specific mode.
        :param device: The device to set to a specific mode.
        :param mode: The mode to set the device in.
        :param temperature: When using .MANUAL: the temperature to set the device to.
        :param minutes: When using .MAX or .MANUAL: the duration of this mode before the device reverts.
        :return: True if the API reported success, False otherwise.
        """
        payload = {
            "device_id": self.relay_id,
            "module_id": self.thermostat_id if device == DeviceType.THERMOSTAT else self.valve_id,
            "setpoint_mode": mode.value,
        }
        if device == DeviceType.VALVE:
            if mode == SetpointMode.OFF:
                minutes = minutes if minutes else 24 * 60
                temperature = 7
                mode = SetpointMode.MANUAL
            payload = {
                "home_id": self.home_id,
                "room_id": self.room_id,
                "mode": mode.value,
            }
        if mode in (SetpointMode.MANUAL, SetpointMode.MAX):
            if not minutes or minutes < 0:
                raise NetatmoInvalidDurationError
            param = "setpoint_endtime" if device == DeviceType.THERMOSTAT else "endtime"
            payload[param] = pendulum.now().add(minutes=minutes).int_timestamp
        if mode == SetpointMode.MANUAL:
            if not temperature or not 7 <= temperature <= 30:
                raise NetatmoInvalidTemperatureError
            param = "setpoint_temp" if device == DeviceType.THERMOSTAT else "temp"
            payload[param] = temperature

        # a thermostat can be controlled directly, but a valve needs to be controlled as part of a room
        endpoint = "/setthermpoint" if device == DeviceType.THERMOSTAT else "/setroomthermpoint"

        result = self._access_server(endpoint=endpoint, payload=payload, data_class=_SetpointChange)

        success = result.status == "ok"  # TODO: does this report an actual change or an accepted request?
        device = "thermostat" if device == DeviceType.THERMOSTAT else "valve"

        if success:
            if mode == SetpointMode.MANUAL:
                log.info("changed the %s to the targeted mode MANUAL at %s°C for %s minutes",
                         device, str(temperature), str(minutes))
            elif mode == SetpointMode.MAX:
                log.info("changed the %s to the targeted mode MAX for %s minutes", device, str(minutes))
            else:
                log.info("changed the %s to the targeted mode %s", device, mode.name)

        else:
            log.info("unable to set the %s to the targeted mode %s", device, mode.name)

        return success


if __name__ == "__main__":
    pass
