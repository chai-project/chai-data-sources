# pylint: disable=line-too-long, missing-module-docstring, missing-class-docstring)

from typing import Any

from dacite import DaciteError
from requests.exceptions import RequestException


class EfergyError(Exception):  # base class to simplify bulk error handling
    pass


class NetatmoError(Exception):  # base class to simplify bulk error handling
    pass


class EfergyServerError(EfergyError):  # the Energyhive server returned a server error when accessed
    pass


class EfergyInvalidTokenError(EfergyError):  # the provided token is invalid
    pass


class EfergyInvalidTimestampError(EfergyError):  # a timestamp returned from the API could not be parsed
    pass


class EfergyNoMeterReadingError(EfergyError):  # all data is there, but there is no meter power reading
    pass


class EfergyUnknownError(EfergyError):  # any other error that does not fit any previous categories
    def __init__(self, data: Any):
        self.relevant_data = data
        super().__init__()


class EfergyNoMeterError(EfergyError):  # no meter was found to get data from
    pass


class EfergyMultipleMetersError(EfergyError):  # multiple meters reported while only one was expected
    pass


class EfergyJSONError(EfergyError):  # the received data is not valid JSON
    pass


class EfergyDataclassError(EfergyError):  # the received data could not be transformed to the expected dataclass
    def __init__(self, error: DaciteError):
        self.upstream_error = error
        super().__init__()


class EfergyConnectionError(EfergyError):  # the server could not be accessed
    def __init__(self, error: RequestException):
        self.upstream_error = error
        super().__init__()


class EfergyAPIAccessError(EfergyError):  # the Energyhive server returned a server error with a description
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class NetatmoConnectionError(NetatmoError):  # the server could not be accessed
    def __init__(self, error: RequestException):
        self.upstream_error = error
        super().__init__()


class NetatmoJSONError(NetatmoError):  # the received data is not valid JSON
    pass


class NetatmoRelayError(NetatmoError):  # an issue occurred when trying to identify the relay (either 0 or 1+)
    pass


class NetatmoThermostatError(NetatmoError):  # an issue occurred when trying to identify the thermostat (either 0 or 1+)
    pass


class NetatmoValveError(NetatmoError):  # an issue occurred when trying to identify the valve (either 0 or 1+)
    pass


class NetatmoBoilerError(NetatmoError):  # an issue occurred when trying to identify the boiler status
    pass


class NetatmoMeasurementError(NetatmoError):  # expected a single measure, but got zero or multiple
    pass


class NetatmoInvalidDurationError(NetatmoError):  # a strictly positive setpoint duration was expected
    pass


class NetatmoInvalidTemperatureError(NetatmoError):  # a temperature in Celsius between 7 and 30 was expected
    pass


class NetatmoInvalidClientError(NetatmoError):  # either the client ID or client secret is invalid
    pass


class NetatmoInvalidTokenError(NetatmoError):  # the token is invalid or does not have the required client permissions
    pass


# dataclass errors indicate that the data received from the API is incorrect or incomplete,
# which could happen when for example the Netatmo thermostatic valve is not accessible or registered
class NetatmoDataclassError(NetatmoError):  # the received data could not be transformed to the expected dataclass
    def __init__(self, error: DaciteError):
        self.upstream_error = error
        super().__init__()


class NetatmoUnknownError(NetatmoError):  # any other error that does not fit any previous categories
    def __init__(self, data: Any):
        self.relevant_data = data
        super().__init__()
