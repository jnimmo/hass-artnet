"""
Home Assistant support for DMX lights over IP.

Date:     2020-04-13
Homepage: https://github.com/jnimmo/hass-dmx
Author:   James Nimmo
"""
import asyncio
import logging
import socket
from struct import pack

from homeassistant.const import (CONF_DEVICES, CONF_HOST, CONF_NAME, CONF_PORT,
                                 CONF_TYPE, STATE_ON, STATE_OFF)
try:
  from homeassistant.components.light import (ATTR_BRIGHTNESS,
                                              ATTR_HS_COLOR,
                                              ATTR_TRANSITION,
                                              ATTR_WHITE_VALUE,
                                              ATTR_COLOR_TEMP,
                                              LightEntity,
                                              PLATFORM_SCHEMA,
                                              SUPPORT_BRIGHTNESS,
                                              SUPPORT_COLOR,
                                              SUPPORT_WHITE_VALUE,
                                              SUPPORT_TRANSITION,
                                              SUPPORT_COLOR_TEMP)
except ImportError:
  from homeassistant.components.light import (ATTR_BRIGHTNESS,
                                              ATTR_HS_COLOR,
                                              ATTR_TRANSITION,
                                              ATTR_WHITE_VALUE,
                                              ATTR_COLOR_TEMP,
                                              Light as LightEntity,
                                              PLATFORM_SCHEMA,
                                              SUPPORT_BRIGHTNESS,
                                              SUPPORT_COLOR,
                                              SUPPORT_WHITE_VALUE,
                                              SUPPORT_TRANSITION,
                                              SUPPORT_COLOR_TEMP)
from homeassistant.util.color import color_rgb_to_rgbw
import homeassistant.helpers.config_validation as cv
import homeassistant.util.color as color_util
import voluptuous as vol

_LOGGER = logging.getLogger(__name__)

DATA_ARTNET = 'light_dmx'

CONF_CHANNEL = 'channel'
CONF_DMX_CHANNELS = 'dmx_channels'
CONF_DEFAULT_COLOR = 'default_rgb'
CONF_DEFAULT_LEVEL = 'default_level'
CONF_DEFAULT_TYPE = 'default_type'
CONF_SEND_LEVELS_ON_STARTUP = 'send_levels_on_startup'
CONF_TRANSITION = ATTR_TRANSITION
CONF_UNIVERSE = 'universe'
CONF_CHANNEL_SETUP = 'channel_setup'

# Light types
CONF_LIGHT_TYPE_DIMMER = 'dimmer'
CONF_LIGHT_TYPE_DRGB = 'drgb'
CONF_LIGHT_TYPE_DRGBW = 'drgbw'
CONF_LIGHT_TYPE_RGB = 'rgb'
CONF_LIGHT_TYPE_RGBA = 'rgba'
CONF_LIGHT_TYPE_RGBAW = 'rgbaw'
CONF_LIGHT_TYPE_RGBD = 'rgbd'
CONF_LIGHT_TYPE_RGBW = 'rgbw'
CONF_LIGHT_TYPE_RGBW_AUTO = 'rgbw_auto'
CONF_LIGHT_TYPE_RGBWD = 'rgbwd'
CONF_LIGHT_TYPE_SWITCH = 'switch'
CONF_LIGHT_TYPE_CUSTOM_WHITE = 'custom_white'
CONF_LIGHT_TYPES = [CONF_LIGHT_TYPE_DIMMER,
                    CONF_LIGHT_TYPE_RGB,
                    CONF_LIGHT_TYPE_RGBA,
                    CONF_LIGHT_TYPE_RGBAW,
                    CONF_LIGHT_TYPE_RGBW_AUTO,
                    CONF_LIGHT_TYPE_SWITCH,
                    CONF_LIGHT_TYPE_RGBD,
                    CONF_LIGHT_TYPE_RGBW,
                    CONF_LIGHT_TYPE_DRGB,
                    CONF_LIGHT_TYPE_DRGBW,
                    CONF_LIGHT_TYPE_RGBWD,
                    CONF_LIGHT_TYPE_CUSTOM_WHITE]

# Number of channels used by each light type
CHANNEL_COUNT_MAP, FEATURE_MAP, COLOR_MAP = {}, {}, {}
CHANNEL_COUNT_MAP[CONF_LIGHT_TYPE_DIMMER] = 1
CHANNEL_COUNT_MAP[CONF_LIGHT_TYPE_RGB] = 3
CHANNEL_COUNT_MAP[CONF_LIGHT_TYPE_RGBA] = 4
CHANNEL_COUNT_MAP[CONF_LIGHT_TYPE_RGBD] = 4
CHANNEL_COUNT_MAP[CONF_LIGHT_TYPE_RGBW] = 4
CHANNEL_COUNT_MAP[CONF_LIGHT_TYPE_RGBAW] = 5
CHANNEL_COUNT_MAP[CONF_LIGHT_TYPE_RGBW_AUTO] = 4
CHANNEL_COUNT_MAP[CONF_LIGHT_TYPE_DRGB] = 4
CHANNEL_COUNT_MAP[CONF_LIGHT_TYPE_DRGBW] = 5
CHANNEL_COUNT_MAP[CONF_LIGHT_TYPE_RGBWD] = 5
CHANNEL_COUNT_MAP[CONF_LIGHT_TYPE_SWITCH] = 1
CHANNEL_COUNT_MAP[CONF_LIGHT_TYPE_CUSTOM_WHITE] = 2

# Features supported by light types
FEATURE_MAP[CONF_LIGHT_TYPE_DIMMER] = (SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION)
FEATURE_MAP[CONF_LIGHT_TYPE_RGB] = (SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION |
                                    SUPPORT_COLOR)
FEATURE_MAP[CONF_LIGHT_TYPE_RGBA] = (SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION |
                                     SUPPORT_COLOR)
FEATURE_MAP[CONF_LIGHT_TYPE_RGBAW] = (SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION |
                                     SUPPORT_COLOR | SUPPORT_WHITE_VALUE)
FEATURE_MAP[CONF_LIGHT_TYPE_RGBD] = (SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION |
                                     SUPPORT_COLOR)
FEATURE_MAP[CONF_LIGHT_TYPE_RGBW] = (SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION |
                                     SUPPORT_COLOR | SUPPORT_WHITE_VALUE)
FEATURE_MAP[CONF_LIGHT_TYPE_RGBW_AUTO] = (SUPPORT_BRIGHTNESS |
                                          SUPPORT_TRANSITION | SUPPORT_COLOR)
FEATURE_MAP[CONF_LIGHT_TYPE_DRGB] = (SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION |
                                     SUPPORT_COLOR)
FEATURE_MAP[CONF_LIGHT_TYPE_DRGBW] = (SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION |
                                      SUPPORT_COLOR | SUPPORT_WHITE_VALUE)
FEATURE_MAP[CONF_LIGHT_TYPE_RGBWD] = (SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION |
                                      SUPPORT_COLOR | SUPPORT_WHITE_VALUE)
FEATURE_MAP[CONF_LIGHT_TYPE_SWITCH] = 0
FEATURE_MAP[CONF_LIGHT_TYPE_CUSTOM_WHITE] = (SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION |
                                     SUPPORT_COLOR_TEMP)

# Default color for each light type if not specified in configuration
COLOR_MAP[CONF_LIGHT_TYPE_DIMMER] = None
COLOR_MAP[CONF_LIGHT_TYPE_RGB] = [255, 255, 255]
COLOR_MAP[CONF_LIGHT_TYPE_RGBA] = [255, 255, 255]
COLOR_MAP[CONF_LIGHT_TYPE_RGBAW] = [255, 255, 255, 255]
COLOR_MAP[CONF_LIGHT_TYPE_RGBD] = [255, 255, 255]
COLOR_MAP[CONF_LIGHT_TYPE_RGBW] = [255, 255, 255]
COLOR_MAP[CONF_LIGHT_TYPE_RGBW_AUTO] = [255, 255, 255]
COLOR_MAP[CONF_LIGHT_TYPE_DRGB] = [255, 255, 255]
COLOR_MAP[CONF_LIGHT_TYPE_DRGBW] = [255, 255, 255]
COLOR_MAP[CONF_LIGHT_TYPE_RGBWD] = [255, 255, 255]
COLOR_MAP[CONF_LIGHT_TYPE_SWITCH] = None
COLOR_MAP[CONF_LIGHT_TYPE_CUSTOM_WHITE] = None

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_UNIVERSE, default=0): cv.byte,
    vol.Optional(CONF_DMX_CHANNELS, default=512): vol.All(vol.Coerce(int),
                                                          vol.Range(min=1,
                                                          max=512)),
    vol.Optional(CONF_DEFAULT_LEVEL, default=255): cv.byte,
    vol.Optional(CONF_DEFAULT_TYPE, default=CONF_LIGHT_TYPE_DIMMER): cv.string,
    vol.Required(CONF_DEVICES): vol.All(cv.ensure_list, [
        {
            vol.Required(CONF_CHANNEL): vol.All(vol.Coerce(int),
                                                vol.Range(min=1, max=512)),
            vol.Optional(CONF_NAME): cv.string,
            vol.Optional(CONF_TYPE): vol.In(CONF_LIGHT_TYPES),
            vol.Optional(CONF_DEFAULT_LEVEL): cv.byte,
            vol.Optional(ATTR_WHITE_VALUE): cv.byte,
            vol.Optional(CONF_DEFAULT_COLOR): vol.All(
                vol.ExactSequence((cv.byte, cv.byte, cv.byte)),
                vol.Coerce(tuple)),
            vol.Optional(CONF_TRANSITION, default=0): vol.All(vol.Coerce(int),
                                                              vol.Range(min=0,
                                                              max=60)),
            vol.Optional(CONF_CHANNEL_SETUP): cv.string,
        }
    ]),
    vol.Optional(CONF_PORT, default=6454): cv.port,
    vol.Optional(CONF_SEND_LEVELS_ON_STARTUP, default=True): cv.boolean,
})


@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    host = config.get(CONF_HOST)
    universe = config.get(CONF_UNIVERSE)
    port = config.get(CONF_PORT)
    send_levels_on_startup = config.get(CONF_SEND_LEVELS_ON_STARTUP)

    # Send the specified default level to pre-fill the channels with
    overall_default_level = config.get(CONF_DEFAULT_LEVEL)
    default_light_type = config.get(CONF_DEFAULT_TYPE)

    dmx_gateway = DMXGateway(host, universe, port, overall_default_level,
                             config[CONF_DMX_CHANNELS])

    lights = (DMXLight(light, dmx_gateway, send_levels_on_startup, default_light_type) for light in
              config[CONF_DEVICES])
    async_add_devices(lights)

    return True


class DMXLight(LightEntity):
    """Representation of a DMX Art-Net light."""

    def __init__(self, light, dmx_gateway, send_immediately, default_type):
        """Initialize DMXLight"""
        self._dmx_gateway = dmx_gateway

        # Fixture configuration
        self._channel = light.get(CONF_CHANNEL)
        self._name = light.get(CONF_NAME, f"DMX Channel {self._channel}")
        
        self._type = light.get(CONF_TYPE, default_type)

        self._fade_time = light.get(CONF_TRANSITION)
        self._brightness = light.get(CONF_DEFAULT_LEVEL,
                                     dmx_gateway.default_level)
        self._rgb = light.get(CONF_DEFAULT_COLOR, COLOR_MAP.get(self._type))
        self._white_value = light.get(ATTR_WHITE_VALUE, 0)
        self._color_temp = int((self.min_mireds + self.max_mireds) / 2)
        self._channel_setup = light.get(CONF_CHANNEL_SETUP, '')

        # Apply maps and calculations
        if self._type == CONF_LIGHT_TYPE_CUSTOM_WHITE:
            self._channel_count = len(self._channel_setup)
        else:
            self._channel_count = CHANNEL_COUNT_MAP.get(self._type, 1)

        self._channels = [channel for channel in range(self._channel,
                                                       self._channel +
                                                       self._channel_count)]
        self._features = FEATURE_MAP.get(self._type)

        # Brightness needs to be set to the maximum default RGB level, then
        # scale up the RGB values to what HA uses
        if self._rgb:
            self._brightness = max(self._rgb) * (self._brightness/255)

        if self._brightness > 0 or self._white_value > 0:
            self._state = STATE_ON
        else:
            self._state = STATE_OFF

        # Send default levels to the controller
        self._dmx_gateway.set_channels(self._channels, self.dmx_values,
                                       send_immediately)

        _LOGGER.debug(f"Intialized DMX light {self._name}")

    @property
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def brightness(self):
        """Return the brightness of the light."""
        return self._brightness

    @property
    def device_state_attributes(self):
        data = {}
        data['dmx_universe'] = self._dmx_gateway._universe
        data['dmx_channels'] = self._channels
        data[CONF_TRANSITION] = self._fade_time
        data['dmx_values'] = self.dmx_values
        return data

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._state == STATE_ON

    @property
    def hs_color(self):
        """Return the HS color value."""
        if self._rgb:
            return color_util.color_RGB_to_hs(*self._rgb)
        else:
            return None

    @property
    def white_value(self):
        """Return the white value of this light between 0..255."""
        if ((self._type == CONF_LIGHT_TYPE_RGBW) or
            (self._type == CONF_LIGHT_TYPE_RGBWD) or
                (self._type == CONF_LIGHT_TYPE_DRGBW)):
            return self._white_value
        else:
            return None

    @property
    def min_mireds(self):
        """Return the coldest color_temp that this light supports."""
        # Default to the Philips Hue value that HA has always assumed
        # https://developers.meethue.com/documentation/core-concepts
        return 192

    @property
    def max_mireds(self):
        """Return the warmest color_temp that this light supports."""
        # Default to the Philips Hue value that HA has always assumed
        # https://developers.meethue.com/documentation/core-concepts
        return 448

    @property
    def dmx_values(self):
        # Select which values to send over DMX

        if self._type == CONF_LIGHT_TYPE_RGB:
            # Scale the RGB colour value to the selected brightness
            return scale_rgb_to_brightness(self._rgb, self._brightness)
        elif self._type == CONF_LIGHT_TYPE_RGBA:
            # Split the white component out from the scaled RGB values
            rgba = scale_rgb_to_brightness(self._rgb, self._brightness)
            amber = rgba[0]
            if (amber > rgba[1] * 2):
                amber = rgba[1] * 2
            rgba[0] = rgba[0] - amber
            rgba[1] = round(rgba[1] - amber/2)
            rgba.append(amber)
            return rgba
        elif self._type == CONF_LIGHT_TYPE_RGBAW:
            # Split the white component out from the scaled RGB values
            values = scale_rgb_to_brightness(self._rgb, self._brightness)
            amber = values[0]
            if (amber > values[1] * 2):
                amber = values[1] * 2
            values[0] = values[0] - amber
            values[1] = round(values[1] - amber/2)
            values.append(amber)
            values.append(round(self._white_value * (self._brightness / 255)))
            return values
        elif self._type == CONF_LIGHT_TYPE_RGBW:
            rgbw = scale_rgb_to_brightness(self._rgb, self._brightness)
            rgbw.append(round(self._white_value * (self._brightness / 255)))
            return rgbw
        elif self._type == CONF_LIGHT_TYPE_RGBW_AUTO:
            # Split the white component out from the scaled RGB values
            scaled_rgb = scale_rgb_to_brightness(self._rgb, self._brightness)
            return color_rgb_to_rgbw(*scaled_rgb)
        elif self._type == CONF_LIGHT_TYPE_DRGB:
            drgb = [self._brightness]
            drgb.extend(self._rgb)
            return drgb
        elif self._type == CONF_LIGHT_TYPE_RGBD:
            return [*self._rgb, round(self._brightness)]
        elif self._type == CONF_LIGHT_TYPE_DRGBW:
            drgbw = [self._brightness]
            drgbw.extend(self._rgb)
            drgbw.append(self._white_value)
            return drgbw
        elif self._type == CONF_LIGHT_TYPE_RGBWD:
            rgbwd = list()
            rgbwd.extend(self._rgb)
            rgbwd.append(self._white_value)
            rgbwd.append(self._brightness)
            return rgbwd
        elif self._type == CONF_LIGHT_TYPE_SWITCH:
            if self.is_on:
                return 255
            else:
                return 0
        elif self._type == CONF_LIGHT_TYPE_CUSTOM_WHITE:
            # d = dimmer
            # c = cool (scaled for brightness)
            # C = cool (not scaled)
            # h = hot (scaled for brightness)
            # H = hot (not scaled)
            # t = temperature (0 = hot, 255 = cold) 
            # T = temperature (255 = hot, 0 = cold)

            ww_fraction = (self._color_temp - self.min_mireds) / (
                           self.max_mireds - self.min_mireds)
            cw_fraction = 1 - ww_fraction
            max_fraction = max(ww_fraction, cw_fraction)

            switcher = {
                'd': self._brightness,
                't': 255 - (ww_fraction * 255),
                'T': ww_fraction * 255,
                'h': self.is_on * self._brightness * (ww_fraction / max_fraction),
                'c': self.is_on * self._brightness * (cw_fraction / max_fraction),
            }

            values = list()
            for channel in self._channel_setup:
                values.append(int(round(switcher.get(channel, 0))))

            return values
        else:
            return self._brightness

    @property
    def color_temp(self):
        """Flag supported features."""
        return self._color_temp

    @property
    def supported_features(self):
        """Flag supported features."""
        return self._features

    @property
    def should_poll(self):
        return False

    @property
    def fade_time(self):
        return self._fade_time

    @fade_time.setter
    def fade_time(self, value):
        self._fade_time = value

    @asyncio.coroutine
    def async_turn_on(self, **kwargs):
        """Instruct the light to turn on.

        Move to using one method on the DMX class to set/fade either a single
        channel or group of channels
        """
        self._state = STATE_ON
        transition = kwargs.get(ATTR_TRANSITION, self._fade_time)

        # Update state from service call
        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs[ATTR_BRIGHTNESS]
        
        if self._brightness == 0:
            self._brightness = 255

        if ATTR_HS_COLOR in kwargs:
            self._rgb = color_util.color_hs_to_RGB(*kwargs[ATTR_HS_COLOR])
            # self._white_value = color_rgb_to_rgbw(*self._rgb)[3]

        if ATTR_WHITE_VALUE in kwargs:
            self._white_value = kwargs[ATTR_WHITE_VALUE]

        if ATTR_COLOR_TEMP in kwargs:
            self._color_temp = kwargs[ATTR_COLOR_TEMP]

        _LOGGER.debug("Setting light '%s' to %s with transition time %i",
                      self._name, repr(self.dmx_values), transition)
        asyncio.ensure_future(
            self._dmx_gateway.set_channels_async(
                self._channels, self.dmx_values, transition=transition))
        self.async_schedule_update_ha_state()

    @asyncio.coroutine
    def async_turn_off(self, **kwargs):
        """Instruct the light to turn off.

        If a transition time has been specified in
        seconds the controller will fade.
        """
        transition = kwargs.get(ATTR_TRANSITION, self._fade_time)

        _LOGGER.debug("Turning off '%s' with transition %i", self._name, transition)
        asyncio.ensure_future(self._dmx_gateway.set_channels_async(
            self._channels, 0, transition=transition))
        self._state = STATE_OFF
        self.async_schedule_update_ha_state()

    def update(self):
        """Fetch update state."""
        # Nothing to return


class DMXGateway(object):
    """
    Class to keep track of the values of DMX channels.
    """

    def __init__(self, host, universe, port, default_level,
                 number_of_channels):
        """
        Initialise a bank of channels, with a default value.
        """

        self._host = host
        self._universe = universe
        self._port = port
        self._number_of_channels = number_of_channels
        self._default_level = default_level

        # Number of channels must be even
        if number_of_channels % 2 != 0:
            self._number_of_channels += 1

        # Initialise the DMX channel array with the default values
        self._channels = [self._default_level] * self._number_of_channels

        # Initialise socket
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # UDP

        packet = bytearray()
        packet.extend(map(ord, "Art-Net"))
        packet.append(0x00)  # Null terminate Art-Net
        packet.extend([0x00, 0x50])  # Opcode ArtDMX 0x5000 (Little endian)
        packet.extend([0x00, 0x0e])  # Protocol version 14
        packet.extend([0x00, 0x00])  # Sequence, Physical
        packet.extend([self._universe, 0x00])  # Universe
        packet.extend(pack('>h', self._number_of_channels))
        self._base_packet = packet

    def send(self):
        """
        Send the current state of DMX values to the gateway via UDP packet.
        """
        # Copy the base packet then add the channel array
        packet = self._base_packet[:]
        packet.extend(self._channels)
        self._socket.sendto(packet, (self._host, self._port))
        _LOGGER.debug("Sending Art-Net frame")

    def set_channels(self, channels, value, send_immediately=True):
        # Single value for standard channels, RGB channels will have 3 or more
        value_arr = [value]
        if type(value) is tuple or type(value) is list:
            value_arr = value

        for x, channel in enumerate(channels):
            default_value = value_arr[min(x, len(value_arr) - 1)]
            self._channels[channel-1] = default_value

        if send_immediately:
            self.send()

    @asyncio.coroutine
    def set_channels_async(self, channels, value, transition=0, fps=40,
                           send_immediately=True):
        original_values = self._channels[:]
        # Minimum of one frame for a snap transition
        number_of_frames = max(int(transition * fps), 1)

        # Single value for standard channels, RGB channels will have 3 or more
        value_arr = [value]
        if type(value) is tuple or type(value) is list:
            value_arr = value

        for i in range(1, number_of_frames+1):
            values_changed = False

            for x, channel in enumerate(channels):
                target_value = value_arr[min(x, len(value_arr) - 1)]
                increment = (target_value -
                             original_values[channel - 1])/(number_of_frames)

                next_value = int(round(
                    original_values[channel - 1] + (increment * i)))

                if self._channels[channel - 1] != next_value:
                    self._channels[channel - 1] = next_value
                    values_changed = True

            if values_changed and send_immediately:
                self.send()

            yield from asyncio.sleep(1. / fps)

    def get_channel_level(self, channel):
        """
        Return the current value we have for the specified channel.
        """
        return self._channels[int(channel)-1]

    @property
    def default_level(self):
        return self._default_level


def scale_rgb_to_brightness(rgb, brightness):
    brightness_scale = (brightness / 255)
    scaled_rgb = [round(rgb[0] * brightness_scale),
                  round(rgb[1] * brightness_scale),
                  round(rgb[2] * brightness_scale)]
    return scaled_rgb
