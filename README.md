# Netatmo/Efergy API Instructions
This package provides access to the Efergy and Netatmo API. Before data can be accessed through the API it is important to register all the devices. For Netatmo specifically an app also needs to be registered.

## Device/App Registration
The device registration is needed to identify you as the owner of the device from which you are trying to access the data. How to do so is specific to the device.

### Efergy meters
The Efergy clamp meter needs to be associated with an Efergy/EnergyHive account. An account can be created on https://www.energyhive.com/content/about/develop . 

> **One Efergy hub per account?**<br>
> At the moment it is unclear whether an EnergyHive account supports multiple hubs. While a hub can connect to multiple meters (a.k.a. clamps), and hence an account can have multiple meters, it is unclear whether an account can have multiple hubs. **The code is currently designed with the assumption that every hub linked to a *single* meter is associated with *one* account.** 

During the installation process of the hub and meter both devices will be associated with the account. Once the hub and meter are successfully linked and data is displayed on EnergyHive an access token can be created. To do so visit https://www.energyhive.com/settings/tokens .

### Netatmo meters
A Netatmo thermostat and its valves need to be associated with a Netatmo account. A new account can be created on https://www.netatmo.com/en-gb .

> **One thermostat per account?**<br>
> With the assumption that the Efergy hub needs a separate account, it makes sense to link the Netatmo device used in the same household to the same account (a.k.a. email address). **The code is designed with this assumption where a single account has a single hub with (due to the trial constraints) a single thermostatic valve.**

Once the Netatmo devices are linked to an account we require an OAuth2 authentication process to obtain an access token. This process authorises an app to access some information from that specific account.

#### Creating a Netatmo app
Only a single Netatmo app needs to be created. **It is advisable that this Netatmo app is created on an account separate from any trial accounts.** An app identifies the purpose of the application. The authorisation of a user gives access to this one app to access only specific data. For the purpose of the trial the access that is requested is to read and write to the thermostat. If an app does not exist yet it can be created at https://dev.netatmo.com/apps/createanapp .

#### Granting Device Permission
For every Netatmo account we need to request permission for this app to access the device. This process is automated when you run the file `netatmo_helper.py`. Make sure that the correct client ID and client secret (as generated in the previous section) are filled in at the bottom of the file. The file `netatmo_helper.py` opens an OAuth2 request, identifies any possible errors, handles the authorisation code, and ultimately provides an access token if all the steps are successful. Both the authorisation token and the renewal token are necessary to access the Netatmo devices.

## Device Access
Once the devices are registered, access can be obtained through the Python API. 

### Efergy Meter
Create an instance of an Efergy meter by providing it with its dedicated access token:

    meter = EfergyMeter(token="token-for-this-meter")

The default way to read the meter is through polling:

    meter.current

The response that is obtained is an instance of `CurrentPower`:

    CurrentPower(value=2223, expires=DateTime(...))

This instance provides the current power in watt (W), as well as the expiry date of this value. The Efergy meter provides new data every 30 seconds. After the `expires` time a new value is available. 

Alternatively, historic data can be accessed using:

    meter.get_historic(start: DateTime, end: DateTime, minutes: Minutes)

The response is an `Iterator`. Either capture this `Iterator` in a `list(...)` or use a `for` loop to iterate over the responses. Each response is an instance of `HistoricPower`:

    HistoricPower(value=0.2, start=DateTime(...), end=DateTime(...))

This instance provides the historic power for the given interval in kilowatts per hour (kWh), along with the start and end date of this interval. The intervals that are aligned match the `minutes` provided when calling the function and are aligned with the hour (i.e. they start at 0 minutes on the hour).

> **Use historic data retrieval sparingly**<br>
> Due to limitations of the Efergy API the `get_historic` method creates an API request for *every* interval. Getting 5-minute intervals for the previous day thus requires 288 API calls. To prevent overloading the API this function is artificially limited to 20 calls per second.

### Netatmo Thermostat
Create an instance of a Netatmo thermostat by providing it with the client ID and client secret of the registered app, as well as the last known valid access token and refresh token:

    client = NetatmoClient(
                 client_id="myapp-id", client_secret="myapp-secret", 
                 refresh_token="622f38e35d51256b8a3b5a55|33fe868a91efadb77b1b46446e2ee9a5"
             )

The client handles the interactions with the API, including the renewal of the access token when it expires. 

#### reading values

Retrieving the thermostat and valve temperature can be done by querying a parameter of the `client` instance:

    client.thermostat_temperature
    client.valve_temperature

For performance reasons, and because temperature generally changes slowly, these values are cached. *Recurring calls within 4 minutes of the original call return the cached values instead of performing another call to the API.*

The different IDs of the devices/concepts are also exposed as parameters of the `client` instance:

    client.relay_id
    client.thermostat_id
    client.valve_id
    client.home_id
    client.room_id  # specially: this is the room in which the valve is located

Historic data can be accessed using:

    client.get_historic(thermostat: True, start: DateTime, end: DateTime, minutes: Minutes)

The response is a list of `HistoricTemperature` instances:

    HistoricTemperature(value=19.7, start=DateTime(...), end=DateTime(...))

This instance provides the historic temperature for the given interval in Celsius, along with the start and end date of this interval. The intervals that are aligned match the `minutes` provided when calling the function and are aligned with the hour (i.e. they start at 0 minutes on the hour).

#### setting values

Using `client` you can also change the setting of the thermostat or the valve. The easiest option is to turn on/off the device. This sets the temperature to 30 °C, or 7 °C, respectively. All requests to turn the heat up require an end time which defaults to 24 hours. For the thermostat, and only when turning the thermostat off, the change persists beyond 24h. The behaviour after the 24h is that the thermostat and valve return to their previous non-overridden state. This can be program mode or frost protection mode. 

    client.turn_off_device(DeviceType.THERMOSTAT)
    client.turn_on_device(DeviceType.VALVE, minutes=60)

> **Changing the valve *may* change the thermostat**<br>
> The API allows the thermostat to be changed directly. However, a valve can only be changed on a room level. If the thermostat is indicated to be in the same room as the valve then changing the valve also changes the value of the thermostat. If both are indicated to be in different rooms then only the valve parameters change.

More detailed control of the thermostat and valve is possible as well:

    client.set_device(device=DeviceType.THERMOSTAT, mode=SetpointMode.MANUAL, temperature=21, minutes=42)

When specifying an attainable temperature – i.e. a temperature that can reasonably be reached in a heated home – the valve will by itself reduce the inflow to the radiator as this temperature is reached. In other words: if you set a valve to e.g. 21 °C and the boiler is on, then the valve does a best effort to close the flow of hot water to ensure the room temperature lands on 21 °C or thereabouts.

All three functions to set the status of a device report back a Boolean value. The value is `True` when the Netatmo API server reports success, of `False` otherwise. 

> **No support for programs/schedules**<br>
> The implementation only allows you to directly control a Netatmo device setpoint instead of through explicit schedules/programs. As a safety feature (?) it appears that the Netatmo API only allows schedules to be *created* or *selected*, **not** *changed* or *removed*. What happens when too many schedules are created is undefined.

#### checking status
Checking whether a thermostat, valve, or boiler is on is a jumbled task, **though one that is now mostly solved**. The `client` exposes the properties `thermostat_on`, `boiler_on`, and `valve_on`. Before using them, you should read this subsection to make sure you understand how these values are retrieved and what the limitations are.

To determine whether the thermostat is on the instance retrieves the setpoint temperature as well as the current room temperature. Doing so is an expensive API call. For this reason checking whether a thermostat is on is behind a 15-second cache. In plain words: after turning a thermostat on, it may take 15 seconds before the `thermostat_on` property returns `True`. 

To determine whether the boiler is on the instance relies on the home information. This is an *very* expensive series of API calls. For this reason checking whether a boiler is on is also behind a 15-second cache. In plain words: after the boiler is turned on (typically by the thermostat), it may take 15 seconds before the `boiler_on` property returns `True`.

Checking whether a valve is on using `valve_on` uses the same expensive series of API call as checking whether a boiler is on. It has the same 15-second cache approach, though checking whether the valve is on is *"free"* as part of checking whether the boiler is on (and vice versa). In addition, there is the property `valve_percentage` which reports the percentage of the valve that is open from 0 to 100. This value cannot be influenced directly and is only provided as information. 