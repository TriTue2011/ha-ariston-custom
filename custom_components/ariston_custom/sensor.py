"""Platform sensor: nhiệt độ nước, nhiệt độ mục tiêu, điện năng tiêu thụ."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AristonEnergyCoordinator, AristonStateCoordinator


@dataclass(frozen=True, kw_only=True)
class AristonSensorDescription(SensorEntityDescription):
    """Mô tả sensor, kèm key đọc từ state dict.

    state_key: key chính (SLP). fallback_key: key của Lydos khi key chính vắng mặt.
    """

    state_key: str
    fallback_key: str = ""


STATE_SENSORS: tuple[AristonSensorDescription, ...] = (
    AristonSensorDescription(
        key="water_temp",
        translation_key="water_temp",
        state_key="waterTemp",
        fallback_key="temp",  # Lydos dùng "temp"
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    AristonSensorDescription(
        key="target_temp",
        translation_key="target_temp",
        state_key="reqTemp",  # Lydos + khớp card water_heater (70°C)
        fallback_key="procReqTemp",  # SLP
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Dựng các sensor."""
    data = hass.data[DOMAIN][entry.entry_id]
    gw: str = data["gw"]
    state_coordinator: AristonStateCoordinator = data["state_coordinator"]
    energy_coordinator: AristonEnergyCoordinator = data["energy_coordinator"]

    entities: list[SensorEntity] = [
        AristonStateSensor(state_coordinator, gw, desc) for desc in STATE_SENSORS
    ]
    entities.append(AristonEnergySensor(energy_coordinator, gw))
    async_add_entities(entities)


class AristonStateSensor(CoordinatorEntity[AristonStateCoordinator], SensorEntity):
    """Sensor đọc từ SlpPlantDataDto (poll 60s)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AristonStateCoordinator,
        gw: str,
        description: AristonSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._state_key = description.state_key
        self._fallback_key = description.fallback_key
        self._attr_unique_id = f"{DOMAIN}_{gw}_{description.key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, gw)})

    @property
    def native_value(self) -> float | None:
        state = self.coordinator.data.get("state", {})
        value = state.get(self._state_key)
        if value is None and self._fallback_key:
            value = state.get(self._fallback_key)
        return float(value) if isinstance(value, (int, float)) else None


class AristonEnergySensor(CoordinatorEntity[AristonEnergyCoordinator], SensorEntity):
    """Sensor điện năng tiêu thụ (kWh), poll riêng 30 phút."""

    _attr_has_entity_name = True
    _attr_translation_key = "energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: AristonEnergyCoordinator, gw: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{gw}_energy"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, gw)})

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data
