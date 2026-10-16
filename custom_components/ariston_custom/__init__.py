"""Khởi tạo integration Ariston Custom."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .api import AristonApiClient, AristonApiError, AristonAuthError
from .const import CONF_GW, CONF_WHE_TYPE, DOMAIN, WHE_TYPE_LYDOS, WHE_TYPES_HO_TRO
from .coordinator import (
    AristonEnergyCoordinator,
    AristonScheduleCoordinator,
    AristonSettingsCoordinator,
    AristonStateCoordinator,
)

PLATFORMS = [Platform.WATER_HEATER, Platform.SENSOR, Platform.SWITCH, Platform.NUMBER]

SERVICE_SET_DHW_SCHEDULE = "set_dhw_schedule"
SERVICE_SET_DHW_SCHEDULE_SIMPLE = "set_dhw_schedule_simple"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Dựng entry: login, tạo coordinator, forward platforms."""
    session = async_get_clientsession(hass)
    client = AristonApiClient(
        session,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    try:
        await client.login()
    except (AristonAuthError, AristonApiError) as err:
        raise ConfigEntryNotReady(f"Không login được Ariston: {err}") from err

    gw: str = entry.data[CONF_GW]
    whe_type = entry.data.get(CONF_WHE_TYPE)
    if whe_type not in WHE_TYPES_HO_TRO:
        raise ConfigEntryNotReady(
            f"wheType={whe_type} chưa được hỗ trợ (hiện hỗ trợ {WHE_TYPES_HO_TRO})"
        )

    state_coordinator = AristonStateCoordinator(hass, client, gw, whe_type)
    await state_coordinator.async_config_entry_first_refresh()
    energy_coordinator = AristonEnergyCoordinator(hass, client, gw)
    await energy_coordinator.async_config_entry_first_refresh()

    # Settings coordinator chỉ cho Lydos (plantSettings: Legionella, nhiệt độ tối đa)
    settings_coordinator: AristonSettingsCoordinator | None = None
    if whe_type == WHE_TYPE_LYDOS:
        settings_coordinator = AristonSettingsCoordinator(hass, client, gw)
        await settings_coordinator.async_config_entry_first_refresh()

    # Schedule coordinator: lịch tuần DHW hiện tại trên máy
    schedule_coordinator = AristonScheduleCoordinator(hass, client, gw)
    await schedule_coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "gw": gw,
        "whe_type": whe_type,
        "state_coordinator": state_coordinator,
        "energy_coordinator": energy_coordinator,
        "settings_coordinator": settings_coordinator,
        "schedule_coordinator": schedule_coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Service đặt lịch tuần DHW: nhận gw và schedule (dict 7 ngày)
    async def _handle_set_dhw_schedule(call: ServiceCall) -> None:
        target_gw: str = call.data["gw"]
        schedule: dict = call.data["schedule"]
        # Tìm client của entry có gw trùng
        for entry_data in hass.data[DOMAIN].values():
            if entry_data.get("gw") == target_gw:
                await entry_data["client"].set_dhw_timeprog(target_gw, schedule)
                return
        raise ValueError(f"Không tìm thấy thiết bị với gw={target_gw}")

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_DHW_SCHEDULE,
        _handle_set_dhw_schedule,
        schema=vol.Schema(
            {
                vol.Required("gw"): cv.string,
                vol.Required("schedule"): dict,
            }
        ),
    )

    # Service đặt lịch đơn giản: chỉ cần thứ, giờ bắt đầu/kết thúc, nhiệt độ.
    # Tự đọc lịch hiện tại, cập nhật khung giờ cho ngày đó, ghi lại.
    async def _handle_set_dhw_schedule_simple(call: ServiceCall) -> None:
        target_gw: str = call.data["gw"]
        day: int = call.data["day"]  # 0=Thứ 2 .. 6=Chủ nhật
        start: str = call.data["start"]  # "HH:MM"
        end: str = call.data["end"]  # "HH:MM"
        temp: float = float(call.data.get("temp", 70))

        def _to_min(t: str) -> int:
            h, m = t.split(":")
            return int(h) * 60 + int(m)

        start_min = _to_min(start)
        end_min = _to_min(end)

        for entry_data in hass.data[DOMAIN].values():
            if entry_data.get("gw") == target_gw:
                client = entry_data["client"]
                # Đọc lịch hiện tại
                current = await client.get_dhw_timeprog(target_gw)
                plans = current.get("plans", [])
                # Đảm bảo đủ 7 ngày
                while len(plans) < 7:
                    plans.append({"slices": []})
                # Cập nhật ngày được chọn: 1 khung đun start->end
                # (giữ nhiệt độ cơ bản ngoài khung giờ)
                base_temp = current.get("baseTemp", 40)
                plans[day] = {
                    "slices": [
                        {"from": 0, "temp": base_temp},
                        {"from": start_min, "temp": temp},
                        {"from": end_min, "temp": base_temp},
                    ]
                }
                new_schedule = {
                    "plans": plans,
                    "allowedTemp": current.get(
                        "allowedTemp", [40, 45, 50, 55, 60, 65, 70]
                    ),
                    "baseTemp": base_temp,
                    "defaultTemp": current.get("defaultTemp", 40),
                }
                await client.set_dhw_timeprog(target_gw, new_schedule)
                # Làm mới sensor lịch ngay
                sched = entry_data.get("schedule_coordinator")
                if sched is not None:
                    await sched.async_request_refresh()
                return
        raise ValueError(f"Không tìm thấy thiết bị với gw={target_gw}")

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_DHW_SCHEDULE_SIMPLE,
        _handle_set_dhw_schedule_simple,
        schema=vol.Schema(
            {
                vol.Required("gw"): cv.string,
                vol.Required("day"): vol.All(vol.Coerce(int), vol.Range(min=0, max=6)),
                vol.Required("start"): cv.string,
                vol.Required("end"): cv.string,
                vol.Optional("temp", default=70): vol.Coerce(float),
            }
        ),
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Gỡ entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        # Gỡ service khi không còn entry nào
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SET_DHW_SCHEDULE)
            hass.services.async_remove(DOMAIN, SERVICE_SET_DHW_SCHEDULE_SIMPLE)
    return unload_ok
