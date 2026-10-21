import logging

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_STREAM_PORT,
    CONF_USERNAME,
    DEFAULT_PORT,
    DEFAULT_STREAM_PORT,
    DOMAIN,
)
from .dvr import ClintonDVRHub

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]
    host = conf[CONF_HOST]
    port = conf.get(CONF_PORT, DEFAULT_PORT)
    username = conf[CONF_USERNAME]
    password = conf.get(CONF_PASSWORD, "")
    stream_port = conf.get(CONF_STREAM_PORT, DEFAULT_STREAM_PORT)

    hub = ClintonDVRHub(hass, host, port, username, password, stream_port)
    hass.data[DOMAIN] = hub

    await hub.start()

    async def _async_stop(event):
        await hub.stop()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)

    hass.async_create_task(
        async_load_platform(hass, "camera", DOMAIN, {}, config)
    )

    return True
