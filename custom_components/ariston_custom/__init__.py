"""Khởi tạo integration Ariston Custom."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AristonApiClient, AristonApiError, AristonAuthError
from .const import CONF_GW, CONF_WHE_TYPE, DOMAIN, WHE_TYPES_HO_TRO
from .coordinator import AristonEnergyCoordinator, AristonStateCoordinator

PLATFORMS = [Platform.WATER_HEATER, Platform.SENSOR]


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
    if whe_type is not None and whe_type not in WHE_TYPES_HO_TRO:
        raise ConfigEntryNotReady(
            f"wheType={whe_type} chưa được hỗ trợ (hiện hỗ trợ {WHE_TYPES_HO_TRO})"
        )

    state_coordinator = AristonStateCoordinator(hass, client, gw, whe_type or 0)
    await state_coordinator.async_config_entry_first_refresh()
    energy_coordinator = AristonEnergyCoordinator(hass, client, gw)
    await energy_coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "gw": gw,
        "whe_type": whe_type,
        "state_coordinator": state_coordinator,
        "energy_coordinator": energy_coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Gỡ entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
