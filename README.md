# Home Assistant DMX over IP Light Platform (Art-Net)

The DMX integration for Home Assistant allows you to send DMX values to an [Art-Net](http://www.art-net.org.uk) capable DMX interface. This component is a one way integration which sends [Art-Net](https://en.wikipedia.org/wiki/Art-Net) UDP packets to the DMX interface. This integration uses no external libraries and requires at least Python version 3.5.

## Prerequisites

* [Home Assistant (hass)](https://www.home-assistant.io/) >= 0.66 in order to use this component.

## Installation

This can be easily installed with the [Home Assistant Community Store (HACS)](https://github.com/custom-components/hacs) using the repository: *jnimmo/hass-dmx*

Alternatively, manual installation by downloading the [custom_components/dmx](custom_components/dmx) directory to the *custom_components/dmx* directory on your Home Assistant instance (generally */config/custom_components/dmx*).

## Configuration

hass-dmx is a community supported Home Assistant integration, if you have any questions you can discuss with the [Home Assistant DMX Community](https://community.home-assistant.io/t/dmx-lighting/2248).

DMX lighting is configured in the `configuration.yaml` file under the *light* domain.

Simplest DMX lighting setup:

```yaml
light:
  - platform: dmx
    host: <IP Address>
    default_type: rgbw
    devices:
      - channel: 1
        name: Dance floor center
      - channel: 2
        name: Dance floor sides
```

More complex DMX lighting configuration:

```yaml
light:
  - platform: dmx
    host: <IP Address>
    port: 6454
    dmx_channels: 512 
    default_level: 255
    universe: 0
    devices:
      - channel: 1
        name: House lights
        type: dimmer
        transition: 3
      - channel: 2
        name: Hall lights
        type: dimmer
        default_level: 255
      - channel: 3
        name: Stair lights
        type: dimmer
        transition: 3
      - channel: 4
        type: rgb
        name: Entrance LED Strip
        default_rgb: [0,0,150]
      - channel: 7
        type: dimmer
        name: Smoke machine
      - channel: 8
        type: custom_white
        name: Intensity/Temperature Light
        channel_setup: dT
```

Configuration variables:
- **host** (*Required*): Art-Net/DMX gateway address
- **port** (*Optional; default=6454*): Art-Net/DMX gateway port
- **universe** (*Optional; default=0*): Art-Net universe for these DMX channels
- **dmx_channels** (*Optional; default=512*): The number of DMX channels to send a value for (even number between 2 & 512)
- **default_level** (*Optional; default=255*): Default level for Home Assistant to assume all lights have been set to - in most cases 0 would make sense. Note Home Assistant will not send these values to the gateway until an explicit change is made unless send_levels_on_startup is True.
- **default_off** (*Optional; default=True*): Whether Home Assistant should assume the device is off by default. See *default_level*.
- **default_type** (*Optional; default=dimmer*): Specify the default type for devices that have not specified a type
- **send_levels_on_startup** (*Optional; default=True*): Setting this to False means Home Assistant will not send any DMX frames until a change is made.

Device configuration variables:
- **channel** (*Required*): The DMX channel for the light (1-512)
- **name** (*Optional; default="DMX Channel #"*): Friendly name for the light (will also be used for the entity_id)
- **type** (*Optional; default=dimmer*): 
  - **'dimmer'** (single channel)
  - **'rgb'** (red, green, blue)
  - **'rgbw'** (red, green, blue, white)
  - **'rgbw_auto'** (red, green, blue, automatically calculated white value) 
  - **'drgb'** (dimmer, red, green, blue)
  - **'drgbw'** (dimmer, red, green, blue, white)
  - **'rgbwd'** (red, green, blue, white, dimmer)
  - **'switch'** (single channel 0 or 255)
  - **'custom_white'** (configure dimmer and temperature in any required channel order)
- **default_level** (*Optional; default=255*): Default level to assume the light is set to (0-255). 
- **default_off** (*Optional; default=True*): Whether Home Assistant should assume the device is off by default. See *default_level*.
- **channel_setup** (*Optional; for custom_white lights*): String to define channel layout where:
  - d = dimmer (brightness 0 to 255)
  - t = temperature (0 = warm, 255 = cold)
  - T = temperature (255 = warm, 0 = cold)
  - h = warm white value (scaled for brightness)
  - c = cool white value (scaled for brightness)
  
Please use [light_profiles.csv](https://www.home-assistant.io/components/light/#default-turn-on-values) if you want to specify a default colour or brightness to be used when turning the light on in HA.
- **default_rgb** (*Optional*): Default colour to give to Home Assistant for the light in the format [R,G,B]
- **white_level** (*Optional*): Default white level for RGBW lights (0-255)
- **transition** (*Optional*): Set a default fade time in seconds for transitions. Can be a decimal number. Transition times specified through the turn_on / turn_off service calls in Home Assistant will override this behaviour. 

To enable debug logging for this component:

```yaml
logger:
  logs:
    custom_components.dmx.light: debug
```

## Features

#### Supported features

- Transition time can be specified through services to fade to a colour (for RGB fixtures) or value. This currently is set to run at 40 frames per second. Multiple fades at the same time seem to be possible.
- Brightness: Once a channel is turned on brightness can be controlled through the Home Assistant interface.
- White level: For RGB lights with a separate white LED this controls the white LED. This can be automatically controlled using the colour wheel on 'rgbw_auto' lights, or manually with 'rgbw'
- Color temperature: For dual channel warm white/cool white fixtures this tunes the white temperature.

#### Limitations

- DMX frames must send values for all channels in a universe. If you have other channels which are controlled by a different device or lighting desk, set Home Assistant to default to 0 values; and set your Art-Net device to merge on highest value rather than most recent update. This means channels could be controlled from either the desk or Home Assistant.

#### Future improvements

- automatically default dmx_channels based on number of configured devices
- device groups/linking

#### Support for other hardware

- Simple, FTDI-chip based USB2DMX cables can be made working with this component through a [UDP proxy implemented in C](https://gist.github.com/zonque/10b7b7183519bf7d3112881cb31b6133).
- DMX King eDMX1
- Enttec ODE MK2

## See Also

* [Art-Net Wikipedia](https://en.wikipedia.org/wiki/Art-Net)
* [Community support for Home Assistant DMX](https://community.home-assistant.io/t/dmx-lighting/2248)

**Art-Net™ Designed by and Copyright Artistic Licence Holdings Ltd**

