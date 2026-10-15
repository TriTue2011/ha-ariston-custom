"""Platform switch: bật/tắt diệt khuẩn Legionella cho Lydos (wheType=3)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SETTING_LEGIONELLA, WHE_TYPE_LYDOS
from .coordinator import AristonSettingsCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Chỉ tạo switch Legionella cho Lydos."""
    data = hass.data[DOMAIN][entry.entry_id]
    if data.get("whe_type") != WHE_TYPE_LYDOS:
        return
    coordinator: AristonSettingsCoordinator = data["settings_coordinator"]
    async_add_entities([AristonLegionellaSwitch(coordinator, data["gw"])])


class AristonLegionellaSwitch(
    CoordinatorEntity[AristonSettingsCoordinator], SwitchEntity
):
    """Công tắc diệt khuẩn Legionella (plantSettings MedAntilegionellaOnOff)."""

    _attr_has_entity_name = True
    _attr_translation_key = "legionella"

    def __init__(self, coordinator: AristonSettingsCoordinator, gw: str) -> None:
        super().__init__(coordinator)
        self._gw = gw
        self._attr_unique_id = f"{DOMAIN}_{gw}_legionella"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, gw)},
            name=f"Ariston {gw}",
            manufacturer="Ariston",
            model="Lydos",
        )

    @property
    def is_on(self) -> bool | None:
        val = self.coordinator.data.get(SETTING_LEGIONELLA)
        if val is None:
            return None
        return bool(val)

    async def async_turn_on(self, **kwargs: Any) -> None:
        old = self.coordinator.data.get(SETTING_LEGIONELLA)
        await self.coordinator.client.set_med_setting(
            self._gw, SETTING_LEGIONELLA, True, old
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        old = self.coordinator.data.get(SETTING_LEGIONELLA)
        await self.coordinator.client.set_med_setting(
            self._gw, SETTING_LEGIONELLA, False, old
        )
        await self.coordinator.async_request_refresh()
