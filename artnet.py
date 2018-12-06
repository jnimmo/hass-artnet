"""
Home Assistant support for Art-Net/DMX lights over IP

Date:     2018-08-14
Homepage: https://github.com/jnimmo/hass-artnet
Author:   James Nimmo

"""
import asyncio
import logging
import socket
from struct import pack
from threading import Thread
import time

from homeassistant.const import (CONF_DEVICES, CONF_HOST, CONF_NAME, CONF_PORT, CONF_TYPE)
from homeassistant.components.light import (ATTR_BRIGHTNESS, ATTR_ENTITY_ID, ATTR_HS_COLOR,
                                            ATTR_TRANSITION, ATTR_WHITE_VALUE, Light,
                                            PLATFORM_SCHEMA, SUPPORT_BRIGHTNESS,
                                            SUPPORT_COLOR, SUPPORT_WHITE_VALUE,
                                            SUPPORT_TRANSITION)
from homeassistant.util.color import color_rgb_to_rgbw
import homeassistant.helpers.config_validation as cv
import homeassistant.util.color as color_util
import voluptuous as vol

_LOGGER = logging.getLogger(__name__)

DATA_ARTNET = 'light_artnet'

CONF_CHANNEL = 'channel'
CONF_DMX_CHANNELS = 'dmx_channels'
CONF_DEFAULT_COLOR = 'default_rgb'
CONF_DEFAULT_LEVEL = 'default_level'
CONF_SEND_LEVELS_ON_STARTUP = 'send_levels_on_startup'
CONF_TRANSITION = ATTR_TRANSITION

# Light types
CONF_LIGHT_TYPE_DIMMER = 'dimmer'
CONF_LIGHT_TYPE_RGB = 'rgb'
CONF_LIGHT_TYPE_RGBW = 'rgbw'
CONF_LIGHT_TYPE_RGBW_AUTO = 'rgbw_auto'
CONF_LIGHT_TYPE_DRGB = 'drgb'
CONF_LIGHT_TYPE_DRGBW = 'drgbw'
CONF_LIGHT_TYPE_RGBWD = 'rgbwd'
CONF_LIGHT_TYPE_SWITCH = 'switch'
CONF_LIGHT_TYPES = [CONF_LIGHT_TYPE_DIMMER, CONF_LIGHT_TYPE_RGB, CONF_LIGHT_TYPE_RGBW_AUTO,
                    CONF_LIGHT_TYPE_SWITCH, CONF_LIGHT_TYPE_RGBW, CONF_LIGHT_TYPE_DRGB, CONF_LIGHT_TYPE_DRGBW, CONF_LIGHT_TYPE_RGBWD]

# Number of channels used by each light type
CHANNEL_COUNT_MAP, FEATURE_MAP, COLOR_MAP = {}, {}, {}
CHANNEL_COUNT_MAP[CONF_LIGHT_TYPE_DIMMER] = 1
CHANNEL_COUNT_MAP[CONF_LIGHT_TYPE_RGB] = 3
CHANNEL_COUNT_MAP[CONF_LIGHT_TYPE_RGBW] = 4
CHANNEL_COUNT_MAP[CONF_LIGHT_TYPE_RGBW_AUTO] = 4
CHANNEL_COUNT_MAP[CONF_LIGHT_TYPE_DRGB] = 4
CHANNEL_COUNT_MAP[CONF_LIGHT_TYPE_DRGBW] = 5
CHANNEL_COUNT_MAP[CONF_LIGHT_TYPE_RGBWD] = 5
CHANNEL_COUNT_MAP[CONF_LIGHT_TYPE_SWITCH] = 1

# Features supported by light types
FEATURE_MAP[CONF_LIGHT_TYPE_DIMMER] = (SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION)
FEATURE_MAP[CONF_LIGHT_TYPE_RGB] = (SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION | SUPPORT_COLOR)
FEATURE_MAP[CONF_LIGHT_TYPE_RGBW] = (SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION | SUPPORT_COLOR | SUPPORT_WHITE_VALUE)
FEATURE_MAP[CONF_LIGHT_TYPE_RGBW_AUTO] = (SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION | SUPPORT_COLOR)
FEATURE_MAP[CONF_LIGHT_TYPE_DRGB] = (SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION | SUPPORT_COLOR)
FEATURE_MAP[CONF_LIGHT_TYPE_DRGBW] = (SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION | SUPPORT_COLOR | SUPPORT_WHITE_VALUE)
FEATURE_MAP[CONF_LIGHT_TYPE_RGBWD] = (SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION | SUPPORT_COLOR | SUPPORT_WHITE_VALUE)
FEATURE_MAP[CONF_LIGHT_TYPE_SWITCH] = ()

# Default color for each light type if not specified in configuration
COLOR_MAP[CONF_LIGHT_TYPE_DIMMER] = None
COLOR_MAP[CONF_LIGHT_TYPE_RGB] = [255, 255, 255]
COLOR_MAP[CONF_LIGHT_TYPE_RGBW] = [255, 255, 255]
COLOR_MAP[CONF_LIGHT_TYPE_RGBW_AUTO] = [255, 255, 255]
COLOR_MAP[CONF_LIGHT_TYPE_DRGB] = [255, 255, 255]
COLOR_MAP[CONF_LIGHT_TYPE_DRGBW] = [255, 255, 255]
COLOR_MAP[CONF_LIGHT_TYPE_RGBWD] = [255, 255, 255] 
COLOR_MAP[CONF_LIGHT_TYPE_SWITCH] = None

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_DMX_CHANNELS, default=512): vol.All(vol.Coerce(int), vol.Range(min=1, max=512)),
    vol.Required(CONF_DEFAULT_LEVEL, default=0): cv.byte,
    vol.Required(CONF_DEVICES): vol.All(cv.ensure_list, [
        {
            vol.Required(CONF_CHANNEL): vol.All(vol.Coerce(int), vol.Range(min=1, max=512)),
            vol.Required(CONF_NAME): cv.string,
            vol.Optional(CONF_TYPE): vol.In(CONF_LIGHT_TYPES),
            vol.Optional(CONF_DEFAULT_LEVEL): cv.byte,
            vol.Optional(ATTR_WHITE_VALUE): cv.byte,
            vol.Optional(CONF_DEFAULT_COLOR): vol.All(
                vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple)),
            vol.Optional(CONF_TRANSITION, default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),

        }
    ]),
    vol.Optional(CONF_PORT, default=6454): cv.port,
    vol.Optional(CONF_SEND_LEVELS_ON_STARTUP, default=True): cv.boolean,
})

@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    host = config.get(CONF_HOST)
    port = config.get(CONF_PORT)
    send_levels_on_startup = config.get(CONF_SEND_LEVELS_ON_STARTUP)

    # Send the specified default level to pre-fill the channels with
    overall_default_level = config.get(CONF_DEFAULT_LEVEL)

    dmx = None
    if not dmx:
        dmx = DMXGateway(host, port, overall_default_level, config[CONF_DMX_CHANNELS])

    lights = (ArtnetLight(light, dmx, send_levels_on_startup) for light in config[CONF_DEVICES])
    async_add_devices(lights)

    return True

class ArtnetLight(Light):
    """Representation of an Artnet Light."""

    def __init__(self, light, controller, send_immediately):
        """Initialize an artnet Light."""
        self._controller = controller

        # Fixture configuration
        self._channel = light.get(CONF_CHANNEL)
        self._name = light.get(CONF_NAME)
        self._type = light.get(CONF_TYPE, CONF_LIGHT_TYPE_DIMMER)
        self._fade_time = light.get(CONF_TRANSITION)
        self._brightness = light.get(CONF_DEFAULT_LEVEL, controller.default_level)
        self._rgb = light.get(CONF_DEFAULT_COLOR, COLOR_MAP.get(self._type))
        self._white_value = light.get(ATTR_WHITE_VALUE, 0)

        # Apply maps and calculations
        self._channel_count = CHANNEL_COUNT_MAP.get(self._type, 1)
        self._channels = [channel for channel in range(self._channel, self._channel + self._channel_count)]
        self._features = FEATURE_MAP.get(self._type)

        # Brightness needs to be set to the maximum default RGB level, then scale up the RGB values to what HA uses
        if self._rgb:
            self._brightness = max(self._rgb)
            self._rgb = scale_rgb_to_brightness(self._rgb, self._brightness)

        logging.debug("Setting default values for '%s' to %s", self._name, repr(self.dmx_values))

        # Send default levels to the controller
        self._controller.set_channels(self._channels, self.dmx_values, send_immediately)

        self._state = self._brightness >= 0 or self._white_value >= 0

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
        data['dmx_channels'] = self._channels
        data[CONF_TRANSITION] = self._fade_time
        data['dmx_values'] = self.dmx_values
        return data

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._state

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
        if ((self._type == CONF_LIGHT_TYPE_RGBW) or (self._type == CONF_LIGHT_TYPE_RGBWD) or (self._type == CONF_LIGHT_TYPE_DRGBW)):
            return self._white_value
        else:
            return None

    @property
    def dmx_values(self):
        # Select which values to send over DMX

        if self._type == CONF_LIGHT_TYPE_RGB:
            # Scale the RGB colour value to the selected brightness
            return scale_rgb_to_brightness(self._rgb, self._brightness)
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
        else:
            return self._brightness

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
        Move to using one method on the DMX class to set/fade either a single channel or group of channels
        """
        self._state = True
        transition = kwargs.get(ATTR_TRANSITION, self._fade_time)

        # Update state from service call
        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs[ATTR_BRIGHTNESS]

        if ATTR_HS_COLOR in kwargs:
            self._rgb = color_util.color_hs_to_RGB(*kwargs[ATTR_HS_COLOR])
            # self._white_value = color_rgb_to_rgbw(*self._rgb)[3]

        if ATTR_WHITE_VALUE in kwargs:
            self._white_value = kwargs[ATTR_WHITE_VALUE]

        logging.debug("Setting light '%s' to values %s with transition time %i", self._name, repr(self.dmx_values),
                      transition)
        asyncio.ensure_future(
            self._controller.set_channels_async(self._channels, self.dmx_values, transition=transition))

        self.async_schedule_update_ha_state()

    @asyncio.coroutine
    def async_turn_off(self, **kwargs):
        """Instruct the light to turn off. If a transition time has been specified in seconds
        the controller will fade."""
        transition = kwargs.get(ATTR_TRANSITION, self._fade_time)

        logging.debug("Turning off '%s' with transition  %i", self._name, transition)
        asyncio.ensure_future(self._controller.set_channels_async(self._channels, 0, transition=transition))
        self._state = False
        self.async_schedule_update_ha_state()

    def update(self):
        """Fetch update state."""
        # Nothing to return


class DMXGateway(object):
    """
    Class to keep track of the values of DMX channels and provide utilities to
    send values to the DMX gateway.
    """

    def __init__(self, host, port, default_level, number_of_channels):
        """
        Initialise a bank of channels, with a default value specified by the caller.
        """

        self._host = host
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
        packet.extend([0x00, 0x00])  # Universe
        packet.extend(pack('>h', self._number_of_channels))  # Pack the number of channels Big endian
        self._base_packet = packet

        # start sending ARTNET
        threa = Thread(target=self.send)

        threa.start()
        self.stopThread = False

    def send(self):
        """
        Send the current state of DMX values to the gateway via UDP packet.
        """
        while True:
            # Copy the base packet then add the channel array
            packet = self._base_packet[:]
            packet.extend(self._channels)
            self._socket.sendto(packet, (self._host, self._port))
            # logging.debug("Sending Art-Net frame")
            time.sleep(1. / 40)

    def set_channels(self, channels, value, send_immediately=True):
        # Single value for standard channels, RGB channels will have 3 or more
        value_arr = [value]
        if type(value) is tuple or type(value) is list:
            value_arr = value

        for x, channel in enumerate(channels):
            default_value = value_arr[min(x, len(value_arr) - 1)]
            self._channels[channel - 1] = default_value

            # if send_immediately:
            # self.send()


    @asyncio.coroutine
    def set_channels_async(self, channels, value, transition=0, fps=40, send_immediately=True):
        original_values = self._channels[:]
        # Minimum of one frame for a snap transition
        number_of_frames = max(int(transition * fps), 1)

        # Single value for standard channels, RGB channels will have 3 or more
        value_arr = [value]
        if type(value) is tuple or type(value) is list:
            value_arr = value

        for i in range(1, number_of_frames + 1):
            values_changed = False

            for x, channel in enumerate(channels):
                target_value = value_arr[min(x, len(value_arr) - 1)]
                increment = (target_value - original_values[channel - 1]) / (number_of_frames)

                next_value = int(round(original_values[channel - 1] + (increment * i)))

                if self._channels[channel - 1] != next_value:
                    self._channels[channel - 1] = next_value
                    values_changed = True

                    # if values_changed and send_immediately:
                    # self.send()

            yield from asyncio.sleep(1. / fps)


    def get_channel_level(self, channel):
        """
        Return the current value we have for the specified channel.
        """
        return self._channels[int(channel) - 1]


    def set_channel_rgb(self, channel, values, send_immediately=True):
        for i in range(0, len(values)):
            logging.debug('Setting channel %i to %i with send immediately = %s', channel + i, values[i], send_immediately)
            if (channel + i <= self._number_of_channels) and (0 <= values[i] <= 255):
                self._channels[channel - 1 + i] = values[i]

        # if send_immediately is True:
        #    self.send()
        return True


    @property
    def default_level(self):
        return self._default_level


    def scale_rgb_to_brightness(rgb, brightness):
        brightness_scale = (brightness / 255)
        scaled_rgb = [round(rgb[0] * brightness_scale),
                      round(rgb[1] * brightness_scale),
                      round(rgb[2] * brightness_scale)]
        return scaled_rgb
