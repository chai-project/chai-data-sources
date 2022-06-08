import re
import unittest
from typing import Dict
from urllib.parse import parse_qs

import pendulum
import requests_mock

from chai_data_sources.exceptions import *
from chai_data_sources.netatmo import NetatmoClient, DeviceType, SetpointMode
from chai_data_sources.utilities import Minutes


def post_body_helper(desired: Dict[str, Any], negate: bool = False):
    """
    Create a matcher that can verify whether the POST body contains the desired elements
    :param desired: The desired parameters and their values.
    :param negate: Whether to negate the result.
    :return: True when all desired parameters are present and the values match, False otherwise.
             True and False responses are switched if the negate parameter is set to True.
    """

    def validate_body(request) -> bool:
        query_components = parse_qs(request.text)
        query_components = {key: next(iter(value), None) for key, value in query_components.items()}
        valid = all([key in query_components and str(value) == query_components[key] for key, value in desired.items()])
        return valid if not negate else not valid

    return validate_body


class NetatmoTests(unittest.TestCase):
    client = NetatmoClient(client_id="my_id", client_secret="my_secret", refresh_token="valid_refresh")
    invalid_client = NetatmoClient(client_id="broken_i", client_secret="my_secret", refresh_token="valid_refresh")
    invalid_refresh = NetatmoClient(client_id="my_id", client_secret="my_secret", refresh_token="broken_refres")
    alt_server_client = NetatmoClient(client_id="my_id", client_secret="my_secret", refresh_token="valid_refresh",
                                      target="https://api.netatmo.com/api_broken")

    def testThermostatTemperature(self):
        # 403 response if access_token is different from "access"

        with requests_mock.Mocker() as mocker:
            endpoints = re.compile(r"^https://api.netatmo.com/.*?$")

            mocker.register_uri(requests_mock.ANY, requests_mock.ANY, text="server error", status_code=500)
            mocker.register_uri("POST", endpoints, status_code=403)

            mocker.register_uri("POST", "https://api.netatmo.com/oauth2/token",
                                additional_matcher=post_body_helper({"client_id": "my_id"}, negate=True),
                                json={"error": "invalid_client"}, status_code=400)
            mocker.register_uri("POST", "https://api.netatmo.com/oauth2/token",
                                additional_matcher=post_body_helper({"client_secret": "my_secret"}, negate=True),
                                json={"error": "invalid_client"}, status_code=400)
            mocker.register_uri("POST", "https://api.netatmo.com/oauth2/token",
                                additional_matcher=post_body_helper({"refresh_token": "valid_refresh"}, negate=True),
                                json={"error": "invalid_grant"}, status_code=400)

            with self.assertRaises(NetatmoInvalidClientError):
                _ = self.invalid_client.thermostat_temperature

            with self.assertRaises(NetatmoInvalidTokenError):
                _ = self.invalid_refresh.thermostat_temperature

            # create an invalid JSON response
            mocker.register_uri("POST", "https://api.netatmo.com/oauth2/token",
                                additional_matcher=post_body_helper({
                                    "grant_type": "refresh_token",
                                    "client_id": "my_id",
                                    "client_secret": "my_secret",
                                    "refresh_token": "valid_refresh"
                                }), text="{broke", status_code=200)

            with self.assertRaises(NetatmoJSONError):
                _ = self.client.thermostat_temperature

            # create an invalid response that is valid JSON
            mocker.register_uri("POST", "https://api.netatmo.com/oauth2/token",
                                additional_matcher=post_body_helper({
                                    "grant_type": "refresh_token",
                                    "client_id": "my_id",
                                    "client_secret": "my_secret",
                                    "refresh_token": "valid_refresh"
                                }), json={"permissions": ["read_thermostat", "write_thermostat"],
                                          "access_token": "access", "refresh_token": "valid_refresh"}, status_code=200)

            with self.assertRaises(NetatmoDataclassError):
                _ = self.client.thermostat_temperature

            # create a valid response to renew the access token
            mocker.register_uri("POST", "https://api.netatmo.com/oauth2/token",
                                additional_matcher=post_body_helper({
                                    "grant_type": "refresh_token",
                                    "client_id": "my_id",
                                    "client_secret": "my_secret",
                                    "refresh_token": "valid_refresh"
                                }), json={"scope": ["read_thermostat", "write_thermostat"],
                                          "access_token": "access", "refresh_token": "valid_refresh",
                                          "expires_in": 10800, "expire_in": 10800}, status_code=200)

            # create additional mocks to handle the thermostats data endpoint
            with self.assertRaises(NetatmoConnectionError):
                _ = self.alt_server_client.thermostat_temperature

            mocker.register_uri("POST", "https://api.netatmo.com/api/getthermostatsdata",
                                additional_matcher=post_body_helper({"access_token": "access"}),
                                text="", status_code=200)

            with self.assertRaises(NetatmoUnknownError):
                _ = self.client.thermostat_temperature

            # create an invalid JSON response
            mocker.register_uri("POST", "https://api.netatmo.com/api/getthermostatsdata",
                                additional_matcher=post_body_helper({"access_token": "access"}),
                                text="{invalid[]}", status_code=200)

            with self.assertRaises(NetatmoJSONError):
                _ = self.client.thermostat_temperature

            # create an invalid response that is valid JSON
            mocker.register_uri("POST", "https://api.netatmo.com/api/getthermostatsdata",
                                additional_matcher=post_body_helper({"access_token": "access"}),
                                json={"body": "value"}, status_code=200)

            with self.assertRaises(NetatmoDataclassError):
                _ = self.client.thermostat_temperature

            # create a valid response to get the thermostatic data
            mocker.register_uri("POST", "https://api.netatmo.com/api/getthermostatsdata",
                                additional_matcher=post_body_helper({"access_token": "access"}),
                                json={"body": {"devices": [
                                    {"_id": "70:ee:50:75:d2:a4", "type": "NAPlug", "last_setup": 1647262562,
                                     "firmware": 222, "last_status_store": 1653819838, "plug_connected_boiler": False,
                                     "wifi_status": 52, "modules": [
                                        {"_id": "04:00:00:75:d1:56", "type": "NATherm1", "firmware": 75,
                                         "last_message": 1653819835, "rf_status": 72, "battery_vp": 3978,
                                         "therm_orientation": 1, "therm_relay_cmd": 1, "anticipating": False,
                                         "module_name": "Thermostat", "battery_percent": 65,
                                         "last_therm_seen": 1653819835, "setpoint": {"setpoint_mode": "program"},
                                         "therm_program_list": [{"timetable": [{"m_offset": 0, "id": 1},
                                                                               {"m_offset": 360, "id": 0},
                                                                               {"m_offset": 960, "id": 1},
                                                                               {"m_offset": 1800, "id": 0},
                                                                               {"m_offset": 2400, "id": 1},
                                                                               {"m_offset": 3240, "id": 0},
                                                                               {"m_offset": 3840, "id": 1},
                                                                               {"m_offset": 4680, "id": 0},
                                                                               {"m_offset": 5280, "id": 1},
                                                                               {"m_offset": 6120, "id": 0},
                                                                               {"m_offset": 6720, "id": 1},
                                                                               {"m_offset": 7560, "id": 0},
                                                                               {"m_offset": 8160, "id": 1},
                                                                               {"m_offset": 9060, "id": 4},
                                                                               {"m_offset": 9660, "id": 1}], "zones": [
                                             {"name": "Comfort", "id": 0, "type": 0, "temp": 19},
                                             {"name": "Comfort +", "id": 3, "type": 8, "temp": 19},
                                             {"name": "Night", "id": 1, "type": 1, "temp": 17},
                                             {"name": "Eco", "id": 4, "type": 5, "temp": 16},
                                             {"type": 2, "id": 2, "temp": 12}, {"type": 3, "id": 5, "temp": 7}],
                                                                 "name": "My schedule",
                                                                 "program_id": "622f3a74b1a160470e1436ed",
                                                                 "selected": True}],
                                         "measured": {"time": 1653824149, "temperature": 19.4, "setpoint_temp": 30}}],
                                     "station_name": "Relay",
                                     "place": {"altitude": 27, "city": "Stenhousemuir", "continent": "Europe",
                                               "country": "GB", "country_name": "United Kingdom",
                                               "location": [-3.814262, 56.025488], "street": "Crownest Loan",
                                               "timezone": "Europe/London"}, "udp_conn": True,
                                     "last_plug_seen": 1653819838}], "user": {"mail": "kim.bauters@bristol.ac.uk",
                                                                              "administrative": {"lang": "en-GB",
                                                                                                 "reg_locale": "en-GB",
                                                                                                 "country": "GB",
                                                                                                 "unit": 0,
                                                                                                 "windunit": 1,
                                                                                                 "pressureunit": 0,
                                                                                                 "feel_like_algo": 0}}},
                                    "status": "ok", "time_exec": 0.08094906806945801, "time_server": 1653827076},
                                status_code=200)

            # create a valid response for the measurement data
            mocker.register_uri("POST", "https://api.netatmo.com/api/getmeasure",
                                additional_matcher=post_body_helper({
                                    "access_token": "access", "device_id": "70:ee:50:75:d2:a4",
                                    "module_id": "04:00:00:75:d1:56", "scale": "max", "type": "Temperature",
                                    "limit": 1, "date_end": "last", "optimize": False
                                }),
                                json={"body": {"1653824149": [19.4]}, "status": "ok", "time_exec": 0.02074885368347168,
                                      "time_server": 1653827076}, status_code=200)

            self.assertEqual(19.4, self.client.thermostat_temperature)
            self.assertEqual("70:ee:50:75:d2:a4", self.client.relay_id)
            self.assertEqual("04:00:00:75:d1:56", self.client.thermostat_id)

            # TODO: historic values
            mocker.register_uri("POST", "https://api.netatmo.com/api/getmeasure",
                                additional_matcher=post_body_helper({
                                    "access_token": "access", "device_id": "70:ee:50:75:d2:a4",
                                    "module_id": "04:00:00:75:d1:56", "scale": "30min", "type": "Temperature",
                                    "limit": 1024, "date_begin": 1653890400, "date_end": 1653912000, "optimize": False
                                }),
                                json={"body": {"1653891300": [18.7], "1653893100": [18.7], "1653894900": [18.8],
                                               "1653896700": [18.9], "1653898500": [19], "1653900300": [19.3],
                                               "1653902100": [19.3], "1653903900": [19.5], "1653905700": [19.6],
                                               "1653907500": [19.7], "1653909300": [19.7], "1653911100": [19.7]},
                                      "status": "ok", "time_exec": 0.2081310749053955, "time_server": 1653997336},
                                status_code=200)

            result = self.client.get_historic(start=pendulum.datetime(2022, 5, 30, 6, 0, 0),
                                              end=pendulum.datetime(2022, 5, 30, 11, 58, 7), minutes=Minutes.MIN_5)

            self.assertEqual(72, len(result))
            self.assertEqual(pendulum.datetime(2022, 5, 30, 6, 0, 0), result[0].start)
            self.assertEqual(pendulum.datetime(2022, 5, 30, 12, 0, 0), result[-1].end)
            self.assertEqual([entry.value for entry in result], [18.7, 18.7, 18.7, 18.7, 18.7, 18.7, 18.7, 18.7, 18.7,
                                                                 18.7, 18.7, 18.7, 18.7, 18.7, 18.7, 18.9, 18.9, 18.9,
                                                                 18.9, 18.9, 18.9, 18.9, 18.9, 18.9, 18.9, 18.9, 18.9,
                                                                 19.3, 19.3, 19.3, 19.3, 19.3, 19.3, 19.3, 19.3, 19.3,
                                                                 19.3, 19.3, 19.3, 19.5, 19.5, 19.5, 19.5, 19.5, 19.5,
                                                                 19.5, 19.5, 19.5, 19.5, 19.5, 19.5, 19.7, 19.7, 19.7,
                                                                 19.7, 19.7, 19.7, 19.7, 19.7, 19.7, 19.7, 19.7, 19.7,
                                                                 19.7, 19.7, 19.7, 19.7, 19.7, 19.7, 19.7, 19.7, 19.7])

            # test setting the thermostat
            with self.assertRaises(NetatmoInvalidTemperatureError):
                _ = self.client.set_device(device=DeviceType.THERMOSTAT, mode=SetpointMode.MANUAL,
                                           temperature=3, minutes=10)

            with self.assertRaises(NetatmoInvalidDurationError):
                _ = self.client.set_device(device=DeviceType.THERMOSTAT, mode=SetpointMode.MANUAL,
                                           minutes=-2)

            with self.assertRaises(NetatmoInvalidTemperatureError):
                _ = self.client.set_device(device=DeviceType.THERMOSTAT, mode=SetpointMode.MANUAL,
                                           minutes=10)

            mocker.register_uri("POST", "https://api.netatmo.com/api/setthermpoint",
                                additional_matcher=post_body_helper({
                                    "device_id": "70:ee:50:75:d2:a4", "module_id": "04:00:00:75:d1:56",
                                    "setpoint_mode": "manual", "setpoint_temp": 30}),
                                json={"status": "ok", "time_exec": 0.017362117767333984, "time_server": 1653835363},
                                status_code=200)

            self.assertTrue(self.client.set_device(device=DeviceType.THERMOSTAT, mode=SetpointMode.MANUAL,
                                                   minutes=10, temperature=30))

    def testValveTemperature(self):
        # many cases are handled in the previous test
        # focus only on those cases that are specific to this endpoint

        with requests_mock.Mocker() as mocker:
            endpoints = re.compile(r"^https://api.netatmo.com/.*?$")

            mocker.register_uri(requests_mock.ANY, requests_mock.ANY, text="server error", status_code=500)
            mocker.register_uri("POST", endpoints, status_code=403)

            # create a valid response to get the access token
            mocker.register_uri("POST", "https://api.netatmo.com/oauth2/token",
                                additional_matcher=post_body_helper({
                                    "grant_type": "refresh_token",
                                    "client_id": "my_id",
                                    "client_secret": "my_secret",
                                    "refresh_token": "valid_refresh"
                                }), json={"scope": ["read_thermostat", "write_thermostat"],
                                          "access_token": "access", "refresh_token": "valid_refresh",
                                          "expires_in": 10800, "expire_in": 10800}, status_code=200)

            # create a valid response to get the thermostatic data
            mocker.register_uri("POST", "https://api.netatmo.com/api/getthermostatsdata",
                                additional_matcher=post_body_helper({"access_token": "access"}),
                                json={"body": {"devices": [
                                    {"_id": "70:ee:50:75:d2:a4", "type": "NAPlug", "last_setup": 1647262562,
                                     "firmware": 222, "last_status_store": 1653819838, "plug_connected_boiler": False,
                                     "wifi_status": 52, "modules": [
                                        {"_id": "04:00:00:75:d1:56", "type": "NATherm1", "firmware": 75,
                                         "last_message": 1653819835, "rf_status": 72, "battery_vp": 3978,
                                         "therm_orientation": 1, "therm_relay_cmd": 1, "anticipating": False,
                                         "module_name": "Thermostat", "battery_percent": 65,
                                         "last_therm_seen": 1653819835, "setpoint": {"setpoint_mode": "program"},
                                         "therm_program_list": [{"timetable": [{"m_offset": 0, "id": 1},
                                                                               {"m_offset": 360, "id": 0},
                                                                               {"m_offset": 960, "id": 1},
                                                                               {"m_offset": 1800, "id": 0},
                                                                               {"m_offset": 2400, "id": 1},
                                                                               {"m_offset": 3240, "id": 0},
                                                                               {"m_offset": 3840, "id": 1},
                                                                               {"m_offset": 4680, "id": 0},
                                                                               {"m_offset": 5280, "id": 1},
                                                                               {"m_offset": 6120, "id": 0},
                                                                               {"m_offset": 6720, "id": 1},
                                                                               {"m_offset": 7560, "id": 0},
                                                                               {"m_offset": 8160, "id": 1},
                                                                               {"m_offset": 9060, "id": 4},
                                                                               {"m_offset": 9660, "id": 1}], "zones": [
                                             {"name": "Comfort", "id": 0, "type": 0, "temp": 19},
                                             {"name": "Comfort +", "id": 3, "type": 8, "temp": 19},
                                             {"name": "Night", "id": 1, "type": 1, "temp": 17},
                                             {"name": "Eco", "id": 4, "type": 5, "temp": 16},
                                             {"type": 2, "id": 2, "temp": 12}, {"type": 3, "id": 5, "temp": 7}],
                                                                 "name": "My schedule",
                                                                 "program_id": "622f3a74b1a160470e1436ed",
                                                                 "selected": True}],
                                         "measured": {"time": 1653824149, "temperature": 19.4, "setpoint_temp": 30}}],
                                     "station_name": "Relay",
                                     "place": {"altitude": 27, "city": "Stenhousemuir", "continent": "Europe",
                                               "country": "GB", "country_name": "United Kingdom",
                                               "location": [-3.814262, 56.025488], "street": "Crownest Loan",
                                               "timezone": "Europe/London"}, "udp_conn": True,
                                     "last_plug_seen": 1653819838}], "user": {"mail": "kim.bauters@bristol.ac.uk",
                                                                              "administrative": {"lang": "en-GB",
                                                                                                 "reg_locale": "en-GB",
                                                                                                 "country": "GB",
                                                                                                 "unit": 0,
                                                                                                 "windunit": 1,
                                                                                                 "pressureunit": 0,
                                                                                                 "feel_like_algo": 0}}},
                                    "status": "ok", "time_exec": 0.08094906806945801, "time_server": 1653827076},
                                status_code=200)

            # create a valid response to get the room data
            mocker.register_uri("POST", "https://api.netatmo.com/api/homesdata",
                                additional_matcher=post_body_helper({"access_token": "access"}),
                                json={"body": {"homes": [
                                    {"id": "622f3a74b1a160470e1436ec", "name": "My Home", "altitude": 27,
                                     "coordinates": [-3.814262, 56.025488], "country": "GB",
                                     "timezone": "Europe/London", "rooms": [
                                        {"id": "628179036", "name": "Living room", "type": "livingroom",
                                         "module_ids": ["04:00:00:75:d1:56"]},
                                        {"id": "1940086014", "name": "Office Room", "type": "custom",
                                         "module_ids": ["09:00:00:15:7a:c2"]}], "modules": [
                                        {"id": "70:ee:50:75:d2:a4", "type": "NAPlug", "name": "Relay",
                                         "setup_date": 1647262562,
                                         "modules_bridged": ["04:00:00:75:d1:56", "09:00:00:15:7a:c2"]},
                                        {"id": "04:00:00:75:d1:56", "type": "NATherm1", "name": "Thermostat",
                                         "setup_date": 1647262563, "room_id": "628179036",
                                         "bridge": "70:ee:50:75:d2:a4"},
                                        {"id": "09:00:00:15:7a:c2", "type": "NRV", "name": "Valve 1",
                                         "setup_date": 1647262670, "room_id": "1940086014",
                                         "bridge": "70:ee:50:75:d2:a4"}], "temperature_control_mode": "heating",
                                     "therm_mode": "schedule", "therm_setpoint_default_duration": 180, "schedules": [{
                                        "timetable": [
                                            {
                                                "zone_id": 1,
                                                "m_offset": 0},
                                            {
                                                "zone_id": 0,
                                                "m_offset": 360},
                                            {
                                                "zone_id": 1,
                                                "m_offset": 960},
                                            {
                                                "zone_id": 0,
                                                "m_offset": 1800},
                                            {
                                                "zone_id": 1,
                                                "m_offset": 2400},
                                            {
                                                "zone_id": 0,
                                                "m_offset": 3240},
                                            {
                                                "zone_id": 1,
                                                "m_offset": 3840},
                                            {
                                                "zone_id": 0,
                                                "m_offset": 4680},
                                            {
                                                "zone_id": 1,
                                                "m_offset": 5280},
                                            {
                                                "zone_id": 0,
                                                "m_offset": 6120},
                                            {
                                                "zone_id": 1,
                                                "m_offset": 6720},
                                            {
                                                "zone_id": 0,
                                                "m_offset": 7560},
                                            {
                                                "zone_id": 1,
                                                "m_offset": 8160},
                                            {
                                                "zone_id": 4,
                                                "m_offset": 9060},
                                            {
                                                "zone_id": 1,
                                                "m_offset": 9660}],
                                        "zones": [
                                            {
                                                "name": "Comfort",
                                                "id": 0,
                                                "type": 0,
                                                "rooms_temp": [
                                                    {
                                                        "room_id": "628179036",
                                                        "temp": 19},
                                                    {
                                                        "room_id": "1940086014",
                                                        "temp": 30}],
                                                "rooms": [
                                                    {
                                                        "id": "628179036",
                                                        "therm_setpoint_temperature": 19},
                                                    {
                                                        "id": "1940086014",
                                                        "therm_setpoint_temperature": 30}]},
                                            {
                                                "name": "Comfort +",
                                                "id": 3,
                                                "type": 8,
                                                "rooms_temp": [
                                                    {
                                                        "room_id": "628179036",
                                                        "temp": 19},
                                                    {
                                                        "room_id": "1940086014",
                                                        "temp": 30}],
                                                "rooms": [
                                                    {
                                                        "id": "628179036",
                                                        "therm_setpoint_temperature": 19},
                                                    {
                                                        "id": "1940086014",
                                                        "therm_setpoint_temperature": 30}]},
                                            {
                                                "name": "Night",
                                                "id": 1,
                                                "type": 1,
                                                "rooms_temp": [
                                                    {
                                                        "room_id": "628179036",
                                                        "temp": 17},
                                                    {
                                                        "room_id": "1940086014",
                                                        "temp": 7}],
                                                "rooms": [
                                                    {
                                                        "id": "628179036",
                                                        "therm_setpoint_temperature": 17},
                                                    {
                                                        "id": "1940086014",
                                                        "therm_setpoint_temperature": 7}]},
                                            {
                                                "name": "Eco",
                                                "id": 4,
                                                "type": 5,
                                                "rooms_temp": [
                                                    {
                                                        "room_id": "628179036",
                                                        "temp": 16},
                                                    {
                                                        "room_id": "1940086014",
                                                        "temp": 7}],
                                                "rooms": [
                                                    {
                                                        "id": "628179036",
                                                        "therm_setpoint_temperature": 16},
                                                    {
                                                        "id": "1940086014",
                                                        "therm_setpoint_temperature": 7}
                                                ]}],
                                        "name": "My schedule",
                                        "default": False,
                                        "away_temp": 12,
                                        "hg_temp": 7,
                                        "id": "622f3a74b1a160470e1436ed",
                                        "selected": True,
                                        "type": "therm"}]}],
                                    "user": {"email": "kim.bauters@bristol.ac.uk", "language": "en-GB",
                                             "locale": "en-GB", "feel_like_algorithm": 0, "unit_pressure": 0,
                                             "unit_system": 0, "unit_wind": 1,
                                             "id": "622f38e35d51256b8a3b5a55"}}, "status": "ok",
                                    "time_exec": 0.9292590618133545, "time_server": 1653827076},
                                status_code=200)

            # create a valid response for the measurement data
            mocker.register_uri("POST", "https://api.netatmo.com/api/getmeasure",
                                additional_matcher=post_body_helper({
                                    "access_token": "access", "device_id": "70:ee:50:75:d2:a4",
                                    "module_id": "09:00:00:15:7a:c2", "scale": "max", "type": "Temperature",
                                    "limit": 1, "date_end": "last", "optimize": False
                                }),
                                json={"body": {"1653824042": [19.3]}, "status": "ok", "time_exec": 0.02802300453186035,
                                      "time_server": 1653827078}, status_code=200)

            self.assertEqual("70:ee:50:75:d2:a4", self.client.relay_id)
            self.assertEqual("04:00:00:75:d1:56", self.client.thermostat_id)
            self.assertEqual("622f3a74b1a160470e1436ec", self.client.home_id)
            self.assertEqual("1940086014", self.client.room_id)
            self.assertEqual("09:00:00:15:7a:c2", self.client.valve_id)
            self.assertEqual(19.3, self.client.valve_temperature)

            mocker.register_uri("POST", "https://api.netatmo.com/api/setroomthermpoint",
                                additional_matcher=post_body_helper({
                                    "home_id": "622f3a74b1a160470e1436ec", "room_id": "1940086014",
                                    "mode": "manual", "temp": 30}),
                                json={"status": "ok", "time_server": 1653835429},
                                status_code=200)

            self.assertTrue(self.client.set_device(device=DeviceType.VALVE, mode=SetpointMode.MANUAL,
                                                   minutes=10, temperature=30))
