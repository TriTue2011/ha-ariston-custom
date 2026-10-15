"""Platform water_heater: entity chính điều khiển bình Ariston (Lydos/SLP)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    LYDOS_MODES,
    MAX_TEMP,
    MIN_TEMP,
    OPERATIVE_MODES,
    PLANT_MODE_MANUAL,
    PLANT_MODE_PROGRAM,
    WHE_TYPE_LYDOS,
)
from .coordinator import AristonStateCoordinator

_LOGGER = logging.getLogger(__name__)

# --- SLP: operation gộp plantMode + operativeMode (re-api-spec.md §7.1, §7.2)
OPERATION_MANUAL = "manual"
SLP_OPERATION_LIST = [OPERATION_MANUAL] + [
    f"program_{name}" for name in OPERATIVE_MODES.values()
]
_SLP_OPERATIVE_NAME_TO_ID = {v: k for k, v in OPERATIVE_MODES.items()}

# --- Lydos: modes đơn giản (LuxPlantMode)
LYDOS_OPERATION_LIST = list(LYDOS_MODES.values())
_LYDOS_NAME_TO_ID = {v: k for k, v in LYDOS_MODES.items()}


def _slp_operation(data: dict[str, Any]) -> str | None:
    plant_mode = data.get("plant_mode")
    state = data.get("state", {})
    if plant_mode == PLANT_MODE_MANUAL:
        return OPERATION_MANUAL
    if plant_mode == PLANT_MODE_PROGRAM:
        op_name = OPERATIVE_MODES.get(state.get("opMode"))
        if op_name:
            return f"program_{op_name}"
    return None


def _lydos_operation(data: dict[str, Any]) -> str | None:
    return LYDOS_MODES.get(data.get("plant_mode"))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Dựng entity water_heater."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: AristonStateCoordinator = data["state_coordinator"]
    async_add_entities(
        [AristonWaterHeater(coordinator, data["gw"], data.get("whe_type"))]
    )


class AristonWaterHeater(CoordinatorEntity[AristonStateCoordinator], WaterHeaterEntity):
    """Bình nóng lạnh Ariston qua cloud API."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
        | WaterHeaterEntityFeature.ON_OFF
    )
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP

    def __init__(
        self, coordinator: AristonStateCoordinator, gw: str, whe_type: int | None
    ) -> None:
        super().__init__(coordinator)
        self._gw = gw
        self._whe_type = whe_type
        self._attr_unique_id = f"{DOMAIN}_{gw}_water_heater"
        model = "Lydos" if whe_type == WHE_TYPE_LYDOS else f"wheType={whe_type}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, gw)},
            name=f"Ariston {gw}",
            manufacturer="Ariston",
            model=model,
        )
        if whe_type == WHE_TYPE_LYDOS:
            self._attr_operation_list = LYDOS_OPERATION_LIST
        else:
            self._attr_operation_list = SLP_OPERATION_LIST

    @property
    def _state(self) -> dict[str, Any]:
        return self.coordinator.data.get("state", {})

    @property
    def _is_lydos(self) -> bool:
        return self._whe_type == WHE_TYPE_LYDOS

    @property
    def current_temperature(self) -> float | None:
        """Nhiệt độ nước hiện tại."""
        return self._state.get("waterTemp", self._state.get("temp"))

    @property
    def target_temperature(self) -> float | None:
        """Nhiệt độ mục tiêu."""
        if self._is_lydos:
            return self._state.get("reqTemp", self._state.get("comfortTemp"))
        return self._state.get("procReqTemp")

    @property
    def current_operation(self) -> str | None:
        data = self.coordinator.data
        if self._is_lydos:
            return _lydos_operation(data)
        return _slp_operation(data)

    @property
    def is_on(self) -> bool | None:
        return self._state.get("on")

    async def async_turn_on(self, **kwargs: Any) -> None:
        client = self.coordinator.client
        if self._is_lydos:
            await client.set_med_switch(self._gw, True)
        else:
            await client.set_switch(self._gw, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        client = self.coordinator.client
        if self._is_lydos:
            await client.set_med_switch(self._gw, False)
        else:
            await client.set_switch(self._gw, False)
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        client = self.coordinator.client
        if self._is_lydos:
            await client.set_med_temperature(self._gw, float(temp))
        else:
            state = self._state
            await client.set_temperatures(
                self._gw,
                comfort=float(temp),
                reduced=float(state.get("reducedTemp", 40.0)),
                old_comfort=state.get("comfortTemp"),
                old_reduced=state.get("reducedTemp"),
            )
        await self.coordinator.async_request_refresh()

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        client = self.coordinator.client
        if self._is_lydos:
            mode_id = _LYDOS_NAME_TO_ID.get(operation_mode)
            if mode_id is None:
                _LOGGER.warning("Operation mode không hợp lệ: %s", operation_mode)
                return
            await client.set_med_mode(self._gw, mode_id)
        else:
            plant_mode = self.coordinator.data.get("plant_mode")
            if operation_mode == OPERATION_MANUAL:
                await client.set_plant_mode(self._gw, PLANT_MODE_MANUAL, plant_mode)
            else:
                op_name = operation_mode.removeprefix("program_")
                op_id = _SLP_OPERATIVE_NAME_TO_ID.get(op_name)
                if op_id is None:
                    _LOGGER.warning("Operation mode không hợp lệ: %s", operation_mode)
                    return
                if plant_mode != PLANT_MODE_PROGRAM:
                    await client.set_plant_mode(self._gw, PLANT_MODE_PROGRAM, plant_mode)
                await client.set_operative_mode(
                    self._gw, op_id, self._state.get("opMode")
                )
        await self.coordinator.async_request_refresh()
