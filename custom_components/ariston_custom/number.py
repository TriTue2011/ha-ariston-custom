"""Platform number: đặt nhiệt độ tối đa cho Lydos (wheType=3)."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MAX_TEMP, MIN_TEMP, SETTING_MAX_TEMP, WHE_TYPE_LYDOS
from .coordinator import AristonSettingsCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Chỉ tạo number nhiệt độ tối đa cho Lydos."""
    data = hass.data[DOMAIN][entry.entry_id]
    if data.get("whe_type") != WHE_TYPE_LYDOS:
        return
    coordinator: AristonSettingsCoordinator = data["settings_coordinator"]
    async_add_entities([AristonMaxTempNumber(coordinator, data["gw"])])


class AristonMaxTempNumber(
    CoordinatorEntity[AristonSettingsCoordinator], NumberEntity
):
    """Nhiệt độ tối đa (plantSettings MedMaxSetpointTemperature)."""

    _attr_has_entity_name = True
    _attr_translation_key = "max_temp"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = MIN_TEMP
    _attr_native_max_value = MAX_TEMP
    _attr_native_step = 1.0

    def __init__(self, coordinator: AristonSettingsCoordinator, gw: str) -> None:
        super().__init__(coordinator)
        self._gw = gw
        self._attr_unique_id = f"{DOMAIN}_{gw}_max_temp"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, gw)},
            name=f"Ariston {gw}",
            manufacturer="Ariston",
            model="Lydos",
        )

    @property
    def native_value(self) -> float | None:
        val = self.coordinator.data.get(SETTING_MAX_TEMP)
        return float(val) if isinstance(val, (int, float)) else None

    async def async_set_native_value(self, value: float) -> None:
        old = self.coordinator.data.get(SETTING_MAX_TEMP)
        await self.coordinator.client.set_med_setting(
            self._gw, SETTING_MAX_TEMP, value, old
        )
        await self.coordinator.async_request_refresh()
