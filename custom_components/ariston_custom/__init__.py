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
    AristonSettingsCoordinator,
    AristonStateCoordinator,
)

PLATFORMS = [Platform.WATER_HEATER, Platform.SENSOR, Platform.SWITCH, Platform.NUMBER]

SERVICE_SET_DHW_SCHEDULE = "set_dhw_schedule"


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

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "gw": gw,
        "whe_type": whe_type,
        "state_coordinator": state_coordinator,
        "energy_coordinator": energy_coordinator,
        "settings_coordinator": settings_coordinator,
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
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Gỡ entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        # Gỡ service khi không còn entry nào
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SET_DHW_SCHEDULE)
    return unload_ok
