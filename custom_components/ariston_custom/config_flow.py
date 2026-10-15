"""Config flow: nhập username/password -> login -> chọn plant -> tạo entry."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AristonApiClient, AristonApiError, AristonAuthError
from .const import CONF_GW, CONF_WHE_TYPE, DOMAIN, WHE_TYPES_HO_TRO

_LOGGER = logging.getLogger(__name__)


class AristonCustomConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Xử lý cấu hình integration."""

    VERSION = 1

    def __init__(self) -> None:
        self._creds: dict[str, str] = {}
        self._plants: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Bước 1: nhập tài khoản Ariston."""
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = AristonApiClient(
                session, user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            try:
                await client.login()
                plants = await client.get_plants()
            except AristonAuthError:
                errors["base"] = "invalid_auth"
            except AristonApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Lỗi không mong đợi khi login Ariston")
                errors["base"] = "unknown"
            else:
                if not plants:
                    errors["base"] = "no_devices"
                else:
                    self._creds = user_input
                    if len(plants) == 1:
                        return await self._create_entry(self._creds, plants[0])
                    self._plants = plants
                    return await self.async_step_select_plant()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_select_plant(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Bước 2 (nếu nhiều plant): chọn thiết bị."""
        if user_input is not None:
            plant = next(
                p for p in self._plants if p.get("gw") == user_input[CONF_GW]
            )
            return self._create_entry(self._creds, plant)

        options = {
            p.get("gw"): f"{p.get('gw')} (wheType {p.get('wheType')})"
            for p in self._plants
        }
        return self.async_show_form(
            step_id="select_plant",
            data_schema=vol.Schema({vol.Required(CONF_GW): vol.In(options)}),
        )

    async def _create_entry(
        self, creds: dict[str, str], plant: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Tạo config entry, lưu usr/pwd để login lại khi token hết hạn."""
        gw = plant.get("psn")
        whe_type = plant.get("wheType")
        # Chống tạo trùng entry cho cùng gateway
        await self.async_set_unique_id(f"{DOMAIN}_{gw}")
        self._abort_if_unique_id_configured()
        if whe_type not in WHE_TYPES_HO_TRO:
            _LOGGER.warning(
                "Plant %s có wheType=%s, integration hiện hỗ trợ %s",
                gw,
                whe_type,
                WHE_TYPES_HO_TRO,
            )
        return self.async_create_entry(
            title=f"Ariston {gw}",
            data={
                CONF_USERNAME: creds[CONF_USERNAME],
                CONF_PASSWORD: creds[CONF_PASSWORD],
                CONF_GW: gw,
                CONF_WHE_TYPE: whe_type,
            },
        )
