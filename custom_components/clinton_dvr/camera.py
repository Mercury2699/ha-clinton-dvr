import logging
from typing import Optional

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    hub = hass.data[DOMAIN]
    
    entities = []
    channels_to_add = hub.active_channels
    for ch in sorted(channels_to_add):
        entities.append(ClintonDVRCamera(hub, ch))
        
    async_add_entities(entities)
    _LOGGER.info("Added %d Clinton DVR camera entities", len(entities))

class ClintonDVRCamera(Camera):
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, hub, channel: int):
        super().__init__()
        self._hub = hub
        self._channel = channel
        
        name_suffix = self._hub.camera_names.get(channel, f"C{channel+1:02d}")
        self._attr_name = f"Clinton DVR {name_suffix}"
        self._attr_unique_id = f"clinton_dvr_camera_{channel}"
        self._attr_is_streaming = True
        self._attr_is_on = True

    @property
    def brand(self) -> str:
        return "Clinton Electronics"

    @property
    def model(self) -> str:
        return "Shadow Series"

    async def async_camera_image(
        self, width: Optional[int] = None, height: Optional[int] = None
    ) -> Optional[bytes]:
        snap = await self._hub.async_get_snapshot(self._channel)
        return snap if snap else None

    async def stream_source(self) -> Optional[str]:
        return f"http://127.0.0.1:{self._hub.stream_port}/live/{self._channel}"
