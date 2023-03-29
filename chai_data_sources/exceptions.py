# pylint: disable=line-too-long, missing-module-docstring, missing-class-docstring)

from typing import Any

from dacite import DaciteError
from requests.exceptions import RequestException


class NetatmoError(Exception):  # base class to simplify bulk error handling
    pass


class NetatmoConnectionError(NetatmoError):  # the server could not be accessed
    def __init__(self, error: RequestException):
        self.upstream_error = error
        super().__init__()

    def __str__(self):
        return "NetatmoConnectionError"


class NetatmoJSONError(NetatmoError):  # the received data is not valid JSON
    pass

    def __str__(self):
        return "NetatmoJSONError"


class NetatmoRelayError(NetatmoError):  # an issue occurred when trying to identify the relay (either 0 or 1+)
    pass

    def __str__(self):
        return "NetatmoRelayError"


class NetatmoThermostatError(NetatmoError):  # an issue occurred when trying to identify the thermostat (either 0 or 1+)
    pass

    def __str__(self):
        return "NetatmoThermostatError"


class NetatmoValveError(NetatmoError):  # an issue occurred when trying to identify the valve (either 0 or 1+)
    pass

    def __str__(self):
        return "NetatmoValveError"


class NetatmoBoilerError(NetatmoError):  # an issue occurred when trying to identify the boiler status
    pass

    def __str__(self):
        return "NetatmoBoilerError"


class NetatmoMeasurementError(NetatmoError):  # expected a single measure, but got zero or multiple
    pass

    def __str__(self):
        return "NetatmoMeasurementError"


class NetatmoInvalidDurationError(NetatmoError):  # a strictly positive setpoint duration was expected
    pass

    def __str__(self):
        return "NetatmoInvalidDurationError"


class NetatmoInvalidTemperatureError(NetatmoError):  # a temperature in Celsius between 7 and 30 was expected
    pass

    def __str__(self):
        return "NetatmoInvalidTemperatureError"


class NetatmoInvalidClientError(NetatmoError):  # either the client ID or client secret is invalid
    pass

    def __str__(self):
        return "NetatmoInvalidClientError"


class NetatmoInvalidTokenError(NetatmoError):  # the token is invalid or does not have the required client permissions
    pass

    def __str__(self):
        return "NetatmoInvalidTokenError"


# dataclass errors indicate that the data received from the API is incorrect or incomplete,
# which could happen when for example the Netatmo thermostatic valve is not accessible or registered
class NetatmoDataclassError(NetatmoError):  # the received data could not be transformed to the expected dataclass
    def __init__(self, error: DaciteError):
        self.upstream_error = error
        super().__init__()

    def __str__(self):
        return "NetatmoDataclassError"


class NetatmoUnknownError(NetatmoError):  # any other error that does not fit any previous categories
    def __init__(self, data: Any):
        self.relevant_data = data
        super().__init__()

    def __str__(self):
        return "NetatmoUnknownError"
