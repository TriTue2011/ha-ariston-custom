"""Client gọi Ariston cloud API (dịch ngược từ APK com.remotethermo.aristonnet).

Quy ước quan trọng (theo re-api-spec.md):
- Header auth là `ar.authToken: <token>` (KHÔNG phải Bearer).
- Token hết hạn (401) -> login lại bằng usr/pwd (API v2 không có refresh-token).
- Body điều khiển theo wrapper {"new": X, "old": Y}; riêng switch/boost là boolean trần.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import API_BASE, AUTH_HEADER, ENERGY_USAGE_SLP, PLANT_DATA_MED, UM_SYS

_LOGGER = logging.getLogger(__name__)


class AristonAuthError(Exception):
    """Sai tài khoản hoặc login thất bại."""


class AristonApiError(Exception):
    """Lỗi gọi API (mã HTTP khác 2xx)."""


class AristonApiClient:
    """Client bất đồng bộ cho Ariston cloud API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._token: str | None = None

    async def login(self) -> str:
        """Đăng nhập, trả về auth token. Gửi đủ body như app thật."""
        url = f"{API_BASE}/v2/accounts/login"
        headers = {"User-Agent": "RestSharp/106.11.7.0"}
        payload = {
            "usr": self._username,
            "pwd": self._password,
            "imp": False,
            "notTrack": True,
            "appInfo": {"appId": "com.remotethermo.aristonnet", "appVer": "7.0.2", "os": "android"},
        }
        async with self._session.post(url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                raise AristonAuthError(f"login thất bại: HTTP {resp.status}")
            data = await resp.json()
        token = data.get("token")
        if not token:
            raise AristonAuthError("login không trả về token")
        self._token = token
        return token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        _retried: bool = False,
    ) -> Any:
        """Gọi API có gắn token; gặp 401 thì login lại 1 lần rồi thử lại."""
        if self._token is None:
            await self.login()
        url = f"{API_BASE}{path}"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "RestSharp/106.11.7.0",
            AUTH_HEADER: self._token,
        }
        async with self._session.request(
            method, url, headers=headers, params=params, json=json_body
        ) as resp:
            if resp.status == 401 and not _retried:
                _LOGGER.debug("Token hết hạn, login lại")
                await self.login()
                return await self._request(
                    method, path, params=params, json_body=json_body, _retried=True
                )
            if resp.status not in (200, 204):
                raise AristonApiError(f"{method} {path} -> HTTP {resp.status}")
            if resp.status == 204 or resp.content_length == 0:
                return None
            return await resp.json()

    # ------------------------------------------------------------------ plants
    async def get_plants(self) -> list[dict[str, Any]]:
        """Liệt kê plant của tài khoản (VelisPlantDto)."""
        data = await self._request("GET", "/v2/velis/plants")
        return data if isinstance(data, list) else []

    # --------------------------------------------- Med plantData (Lydos, wheType=3)
    def _med(self, gw: str, suffix: str = "") -> str:
        return f"/v2/velis/{PLANT_DATA_MED}/{gw}{suffix}"

    async def get_med_state(self, gw: str) -> dict[str, Any]:
        """Đọc trạng thái Lydos (medPlantData)."""
        data = await self._request("GET", self._med(gw), params={"umSys": UM_SYS})
        return data if isinstance(data, dict) else {}

    async def set_med_switch(self, gw: str, on: bool) -> None:
        """Bật/tắt nguồn Lydos. Body boolean trần."""
        await self._request("POST", self._med(gw, "/switch"), json_body=on)

    async def set_med_mode(self, gw: str, new: int) -> None:
        """Đổi mode Lydos (Manual=1/Program=5/Boost=9). Body {"new": value}."""
        await self._request("POST", self._med(gw, "/mode"), json_body={"new": new})

    async def set_med_temperature(self, gw: str, new: float) -> None:
        """Đặt nhiệt độ Lydos. Body {"new": value}."""
        await self._request(
            "POST", self._med(gw, "/temperature"), json_body={"new": new}
        )

    async def set_med_eco(self, gw: str, on: bool) -> None:
        """Bật/tắt ECO Lydos. Body boolean trần."""
        await self._request("POST", self._med(gw, "/switchEco"), json_body=on)

    # --------------------------------------- Med plantSettings (Lydos, wheType=3)
    async def get_med_settings(self, gw: str) -> dict[str, Any]:
        """Đọc plantSettings Lydos: dict key -> value."""
        data = await self._request("GET", self._med(gw, "/plantSettings"))
        return data if isinstance(data, dict) else {}

    async def set_med_setting(
        self, gw: str, key: str, new: Any, old: Any
    ) -> None:
        """Ghi một setting Lydos. Body {key: {"new": X, "old": Y}}."""
        await self._request(
            "POST", self._med(gw, "/plantSettings"), json_body={key: {"new": new, "old": old}}
        )

    # ------------------------------------------------- Lịch tuần DHW (remote)
    async def get_dhw_timeprog(self, gw: str) -> dict[str, Any]:
        """Đọc lịch tuần nước nóng: PackedWeeklyPlanDto."""
        data = await self._request("GET", f"/v2/remote/timeProgs/{gw}/Dhw")
        return data if isinstance(data, dict) else {}

    async def set_dhw_timeprog(self, gw: str, plan: dict[str, Any]) -> None:
        """Ghi lịch tuần nước nóng: body PackedWeeklyPlanDto."""
        await self._request("POST", f"/v2/remote/timeProgs/{gw}/Dhw", json_body=plan)

    # ------------------------------------------------- SLP plantData (SLIM TOP)
    def _slp(self, gw: str, suffix: str = "") -> str:
        return f"/v2/velis/slpPlantData/{gw}{suffix}"

    async def get_slp_state(self, gw: str) -> dict[str, Any]:
        """Đọc trạng thái (SlpPlantDataDto): on, waterTemp, comfortTemp, ..."""
        data = await self._request("GET", self._slp(gw), params={"umSys": UM_SYS})
        return data if isinstance(data, dict) else {}

    # plantMode KHÔNG có endpoint GET riêng trong APK (IWheSlpPlantDataProxy
    # chỉ có setPlantMode); mode hiện tại nằm sẵn trong SlpPlantDataDto ở
    # field JSON "mode" (@SerialName của plantMode). Đọc từ state, đừng GET.

    async def set_switch(self, gw: str, on: bool) -> None:
        """Bật/tắt nguồn. Body là boolean trần."""
        await self._request("POST", self._slp(gw, "/switch"), json_body=on)

    async def set_plant_mode(self, gw: str, new: int, old: int | None) -> None:
        """Đổi Program(1)/Manual(2). Body ChangeValueDto."""
        await self._request(
            "POST", self._slp(gw, "/plantMode"), json_body={"new": new, "old": old}
        )

    async def set_operative_mode(self, gw: str, new: int, old: int | None) -> None:
        """Đổi operative mode (Green=0 ... GreenPlus=6)."""
        await self._request(
            "POST", self._slp(gw, "/operativeMode"), json_body={"new": new, "old": old}
        )

    async def set_temperatures(
        self,
        gw: str,
        comfort: float,
        reduced: float,
        old_comfort: float | None,
        old_reduced: float | None,
    ) -> None:
        """Đặt nhiệt độ comfort/reduced."""
        await self._request(
            "POST",
            self._slp(gw, "/temperatures"),
            json_body={
                "new": {"comfort": comfort, "reduced": reduced},
                "old": {"comfort": old_comfort, "reduced": old_reduced},
            },
        )

    # ----------------------------------------------------------------- energy
    async def get_energy_total(self, gw: str) -> float:
        """Tổng điện năng (kWh) từ /v2/velis/reports."""
        data = await self._request(
            "GET",
            f"/v2/velis/reports/{gw}",
            params={"usages": ENERGY_USAGE_SLP},
        )
        total = 0.0
        if isinstance(data, list):
            for seq in data:
                values = seq.get("v") if isinstance(seq, dict) else None
                if isinstance(values, list):
                    total += sum(v for v in values if isinstance(v, (int, float)))
        return total
