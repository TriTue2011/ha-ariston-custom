"""DataUpdateCoordinator: poll trạng thái 60s, năng lượng 30 phút."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import AristonApiClient
from .const import SCAN_INTERVAL_ENERGY, SCAN_INTERVAL_STATE, WHE_TYPE_LYDOS

_LOGGER = logging.getLogger(__name__)


class AristonStateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll trạng thái: Lydos (medPlantData) hoặc SLP (slpPlantData)."""

    def __init__(
        self, hass: HomeAssistant, client: AristonApiClient, gw: str, whe_type: int
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"ariston_custom {gw}",
            update_interval=SCAN_INTERVAL_STATE,
        )
        self.client = client
        self.gw = gw
        self.whe_type = whe_type

    async def _async_update_data(self) -> dict[str, Any]:
        if self.whe_type == WHE_TYPE_LYDOS:
            state = await self.client.get_med_state(self.gw)
            # medPlantData: mode nằm ở field "mode"
            return {"state": state, "plant_mode": state.get("mode")}
        # SlpPlantDataDto đã chứa sẵn plant mode ở field JSON "mode"
        # (@SerialName của plantMode trong APK; không tồn tại GET .../plantMode)
        state = await self.client.get_slp_state(self.gw)
        return {"state": state, "plant_mode": state.get("mode")}


class AristonEnergyCoordinator(DataUpdateCoordinator[float]):
    """Poll năng lượng riêng (tắt mặc định trong app, poll thưa 30 phút)."""

    def __init__(
        self, hass: HomeAssistant, client: AristonApiClient, gw: str
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"ariston_custom {gw} energy",
            update_interval=SCAN_INTERVAL_ENERGY,
        )
        self.client = client
        self.gw = gw

    async def _async_update_data(self) -> float:
        return await self.client.get_energy_total(self.gw)
