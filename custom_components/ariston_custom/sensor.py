"""Platform sensor: nhiệt độ nước, nhiệt độ mục tiêu, điện năng tiêu thụ, lịch đun."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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
from .coordinator import (
    AristonEnergyCoordinator,
    AristonScheduleCoordinator,
    AristonStateCoordinator,
)


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
    schedule_coordinator: AristonScheduleCoordinator = data["schedule_coordinator"]

    entities: list[SensorEntity] = [
        AristonStateSensor(state_coordinator, gw, desc) for desc in STATE_SENSORS
    ]
    entities.append(AristonEnergySensor(energy_coordinator, gw))
    entities.append(AristonScheduleSensor(schedule_coordinator, gw))
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


TEN_THU = ("Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật")


def _phut_thanh_gio(phut: int) -> str:
    """Phút từ 0h -> "HH:MM"."""
    return f"{phut // 60:02d}:{phut % 60:02d}"


def _khung_dun(plan_ngay: dict) -> list[tuple[int, int, float]]:
    """Trích các khung đun (bắt đầu, kết thúc, nhiệt độ) từ slices của một ngày.

    PackedDailyPlanDto: slices = [{from: phút, temp}]; slice có temp cao hơn
    slice đầu ngày (nhiệt độ cơ bản) là bắt đầu đun, slice tiếp theo trả về
    nhiệt độ cơ bản là kết thúc đun.
    """
    slices = plan_ngay.get("slices", []) if isinstance(plan_ngay, dict) else []
    if not isinstance(slices, list) or not slices:
        return []
    base = slices[0].get("temp") if isinstance(slices[0], dict) else None
    if not isinstance(base, (int, float)):
        base = 40
    khung: list[tuple[int, int, float]] = []
    bat_dau: int | None = None
    nhiet_do: float = 0
    for s in slices:
        if not isinstance(s, dict):
            continue
        frm = s.get("from")
        temp = s.get("temp")
        if not isinstance(frm, (int, float)) or not isinstance(temp, (int, float)):
            continue
        if temp > base and bat_dau is None:
            bat_dau, nhiet_do = int(frm), float(temp)
        elif temp <= base and bat_dau is not None:
            khung.append((bat_dau, int(frm), nhiet_do))
            bat_dau = None
    if bat_dau is not None:  # đun tới hết ngày
        khung.append((bat_dau, 1440, nhiet_do))
    return khung


class AristonScheduleSensor(CoordinatorEntity[AristonScheduleCoordinator], SensorEntity):
    """Sensor lịch đun nước nóng: giá trị = tóm tắt lịch HÔM NAY, attributes = 7 ngày.

    Dữ liệu đọc từ máy (poll 15 phút), không phải lịch mong muốn.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "dhw_schedule"

    def __init__(self, coordinator: AristonScheduleCoordinator, gw: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{gw}_dhw_schedule"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, gw)})

    def _plans(self) -> list[dict]:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return []
        plans = data.get("plans")
        return plans if isinstance(plans, list) else []

    @property
    def native_value(self) -> str | None:
        plans = self._plans()
        if not plans:
            return None
        hom_nay = datetime.now().weekday()  # 0 = Thứ 2
        plan = plans[hom_nay] if hom_nay < len(plans) else {}
        khung = _khung_dun(plan if isinstance(plan, dict) else {})
        if not khung:
            return "Hôm nay không đun"
        return "; ".join(
            f"{_phut_thanh_gio(b)}–{_phut_thanh_gio(e)} · {t:g}°C"
            for b, e, t in khung
        )

    @property
    def extra_state_attributes(self) -> dict:
        plans = self._plans()
        lich: dict[str, list[dict]] = {}
        for i in range(7):
            plan = plans[i] if i < len(plans) and isinstance(plans[i], dict) else {}
            lich[TEN_THU[i]] = [
                {
                    "tu": _phut_thanh_gio(b),
                    "den": _phut_thanh_gio(e),
                    "nhiet_do": t,
                }
                for b, e, t in _khung_dun(plan)
            ]
        return {"lich_tuan": lich}
