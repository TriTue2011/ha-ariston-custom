"""Platform switch: Legionella và ECO cho Lydos (wheType=3)."""

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
from .coordinator import AristonSettingsCoordinator, AristonStateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Tạo switch Legionella + ECO cho Lydos."""
    data = hass.data[DOMAIN][entry.entry_id]
    if data.get("whe_type") != WHE_TYPE_LYDOS:
        return
    gw = data["gw"]
    settings_coordinator: AristonSettingsCoordinator = data["settings_coordinator"]
    state_coordinator: AristonStateCoordinator = data["state_coordinator"]
    async_add_entities(
        [
            AristonLegionellaSwitch(settings_coordinator, gw),
            AristonEcoSwitch(state_coordinator, gw),
        ]
    )


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
        # Fork gửi float 1.0/0.0 cho antilegionella (không phải boolean)
        old = self.coordinator.data.get(SETTING_LEGIONELLA)
        await self.coordinator.client.set_med_setting(
            self._gw, SETTING_LEGIONELLA, 1.0, old
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        old = self.coordinator.data.get(SETTING_LEGIONELLA)
        await self.coordinator.client.set_med_setting(
            self._gw, SETTING_LEGIONELLA, 0.0, old
        )
        await self.coordinator.async_request_refresh()


class AristonEcoSwitch(CoordinatorEntity[AristonStateCoordinator], SwitchEntity):
    """Công tắc chế độ ECO Lydos (POST /switchEco, body boolean)."""

    _attr_has_entity_name = True
    _attr_translation_key = "eco"

    def __init__(self, coordinator: AristonStateCoordinator, gw: str) -> None:
        super().__init__(coordinator)
        self._gw = gw
        self._attr_unique_id = f"{DOMAIN}_{gw}_eco"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, gw)},
            name=f"Ariston {gw}",
            manufacturer="Ariston",
            model="Lydos",
        )

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.data.get("state", {})
        # Thử các field có thể chứa trạng thái ECO
        for key in ("eco", "ecoMode", "isEco"):
            val = state.get(key)
            if val is not None:
                return bool(val)
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_med_eco(self._gw, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_med_eco(self._gw, False)
        await self.coordinator.async_request_refresh()
