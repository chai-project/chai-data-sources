import json
import re
import unittest

import pendulum
import requests_mock

from chai_data_sources.efergy import EfergyMeter, Minutes, HistoricPower
from chai_data_sources.exceptions import *


class EfergyTests(unittest.TestCase):
    meter = EfergyMeter(token="valid-mock-token")
    invalid_token_meter = EfergyMeter(token="broken-toke")
    alt_server_meter = EfergyMeter(token="valid-mock-token", target="http://www.energyhive.com/mobile_proxy_broken")

    def testCurrent(self):
        mock_value = [{"cid": "PWER", "data": [{"1653571435000": 352}], "sid": "853362", "units": "W", "age": 8}]

        with requests_mock.Mocker() as mocker:
            endpoints = re.compile(r"^http://www\.energyhive\.com/mobile_proxy/getCurrentValuesSummary\?token=.*?$")
            valid_endpoint = "http://www.energyhive.com/mobile_proxy/getCurrentValuesSummary?token=valid-mock-token"

            mocker.register_uri(requests_mock.ANY, requests_mock.ANY, text="server error", status_code=500)
            mocker.register_uri("GET", endpoints, json={"status": "error", "description": "Bad token"}, status_code=200)
            mocker.register_uri("GET", valid_endpoint, json=mock_value, status_code=200)

            power = self.meter.get_current()
            self.assertEqual(power.value, 352)
            self.assertEqual(power.expires, pendulum.from_timestamp(1653571435 + 30))

            with self.assertRaises(EfergyInvalidTokenError):
                _ = self.invalid_token_meter.get_current()

            with self.assertRaises(EfergyServerError):
                _ = self.alt_server_meter.get_current()  # call to invalid endpoint throws error

            # create an invalid empty response
            mocker.register_uri("GET", valid_endpoint, text="", status_code=200)

            with self.assertRaises(EfergyUnknownError):
                _ = self.meter.get_current()

            # create an invalid JSON response
            mocker.register_uri("GET", valid_endpoint, text=json.dumps(mock_value)[:-1], status_code=200)

            with self.assertRaises(EfergyJSONError):
                _ = self.meter.get_current()

            # create an invalid response that is valid JSON
            mock_dict = mock_value[0]
            del mock_dict["sid"]
            alt_mock_value = [mock_dict]

            mocker.register_uri("GET", valid_endpoint, json=alt_mock_value, status_code=200)

            with self.assertRaises(EfergyDataclassError):
                _ = self.meter.get_current()

            # create a server error reported by the server
            mocker.register_uri("GET", endpoints, json={"status": "error", "desc": "Server down"}, status_code=200)
            with self.assertRaises(EfergyAPIAccessError):
                _ = self.meter.get_current()

            # create a response without meter data
            alt_value = [{"cid": "PWER", "data": [], "sid": "853362", "units": "W", "age": 8}]
            mocker.register_uri("GET", valid_endpoint, json=alt_value, status_code=200)

            with self.assertRaises(EfergyNoMeterReadingError):
                _ = self.meter.get_current()

            # create a response with no meters
            alt_value = []
            mocker.register_uri("GET", valid_endpoint, json=alt_value, status_code=200)

            with self.assertRaises(EfergyNoMeterError):
                _ = self.meter.get_current()

            # create a response with multiple meters
            alt_value = [
                {"cid": "PWER", "data": [{"1653571435000": 352}], "sid": "853362", "units": "W", "age": 8},
                {"cid": "PWER", "data": [{"1653571427000": 251}], "sid": "746158", "units": "W", "age": 23}
            ]
            mocker.register_uri("GET", valid_endpoint, json=alt_value, status_code=200)

            with self.assertRaises(EfergyMultipleMetersError):
                _ = self.meter.get_current()

    def testHistoric(self):
        with self.assertRaises(ValueError):
            _ = list(self.meter.get_historic(start=pendulum.datetime(2022, 5, 28, 10, 0, 0),
                                             end=pendulum.datetime(2022, 5, 28, 9, 0, 0),
                                             minutes=Minutes.MIN_5))

        with requests_mock.Mocker() as mocker:
            generic_response = {"sum": "0.00", "duration": 900, "units": "kWh"}
            mocker.register_uri("GET", requests_mock.ANY, json=generic_response, status_code=200)

            start = "http://www.energyhive.com/mobile_proxy/getEnergy?fromTime="
            end = "&period=custom&offset=-60&token=valid-mock-token"

            mocker.register_uri(requests_mock.ANY, requests_mock.ANY, text="server error", status_code=500)
            mocker.register_uri("GET", requests_mock.ANY, json=generic_response, status_code=200)
            mocker.register_uri("GET", f"{start}1653439500&toTime=1653440400{end}",
                                json={"sum": "0.09", "duration": 900, "units": "kWh"}, status_code=200)
            mocker.register_uri("GET", f"{start}1653440400&toTime=1653441300{end}",
                                json={"sum": "0.39", "duration": 900, "units": "kWh"}, status_code=200)
            mocker.register_uri("GET", f"{start}1653441300&toTime=1653442200{end}",
                                json={"sum": "0.18", "duration": 900, "units": "kWh"}, status_code=200)

            result = list(
                self.meter.get_historic(start=pendulum.datetime(2022, 5, 25, 1, 45, 0, tz="Europe/London"),
                                        end=pendulum.datetime(2022, 5, 25, 2, 30, 0, tz="Europe/London"),
                                        minutes=Minutes.MIN_15)
            )

            expected = [
                HistoricPower(0.09,
                              pendulum.datetime(2022, 5, 25, 1, 45, 0, tz="Europe/London"),
                              pendulum.datetime(2022, 5, 25, 2, 0, 0, tz="Europe/London")),
                HistoricPower(0.39,
                              pendulum.datetime(2022, 5, 25, 2, 0, 0, tz="Europe/London"),
                              pendulum.datetime(2022, 5, 25, 2, 15, 0, tz="Europe/London")),
                HistoricPower(0.18,
                              pendulum.datetime(2022, 5, 25, 2, 15, 0, tz="Europe/London"),
                              pendulum.datetime(2022, 5, 25, 2, 30, 0, tz="Europe/London")),
            ]

            self.assertEqual(result, expected)

            result = list(
                self.meter.get_historic(start=pendulum.datetime(2022, 5, 25, 1, 47, 12, tz="Europe/London"),
                                        end=pendulum.datetime(2022, 5, 25, 2, 23, 50, tz="Europe/London"),
                                        minutes=Minutes.MIN_15)
            )

            self.assertEqual(result, expected)
