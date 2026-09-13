"""KiwiVM API 客户端：所有出站调用的唯一出口（规格 §13）。"""

import httpx


class KiwiVMError(Exception):
    """KiwiVM 调用失败。code 为 API 返回的 error 字段；-1 表示网络/解析层失败。"""

    def __init__(self, code: int, message: str = ""):
        self.code = code
        self.message = message or f"KiwiVM error {code}"
        super().__init__(self.message)


class KiwiVMClient:
    BASE_URL = "https://api.64clouds.com/v1/"
    TIMEOUT = 20.0  # getLiveServiceInfo 官方提示最长 15s（规格 §5）

    def __init__(self, veid: str, api_key: str, http: httpx.AsyncClient | None = None):
        self.veid = veid
        self.api_key = api_key
        self._owns_http = http is None
        self._http = http or httpx.AsyncClient(timeout=self.TIMEOUT)

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def _call(self, action: str, **params) -> dict:
        query = {"veid": self.veid, "api_key": self.api_key, **params}
        for attempt in (1, 2):  # 网络层失败立即重试 1 次（规格 §7）
            try:
                resp = await self._http.get(self.BASE_URL + action, params=query)
                if resp.status_code != 200:
                    raise KiwiVMError(-1, f"HTTP {resp.status_code}")
                data = resp.json()
            except (httpx.TransportError, ValueError):
                if attempt == 2:
                    raise KiwiVMError(-1, "网络错误或响应无法解析（已重试）")
                continue
            if data.get("error"):
                raise KiwiVMError(data["error"], str(data.get("message", "")))
            return data
        raise KiwiVMError(-1, "unreachable")  # 理论不可达

    async def get_live_service_info(self) -> dict:
        return await self._call("getLiveServiceInfo")

    async def get_service_info(self) -> dict:
        return await self._call("getServiceInfo")

    async def get_rate_limit_status(self) -> dict:
        return await self._call("getRateLimitStatus")

    # ---------- 电源与快照（M3；action 属 start/stop/restart/kill，由路由层校验） ----------

    async def power(self, action: str) -> dict:
        return await self._call(action)

    async def snapshot_list(self) -> dict:
        return await self._call("snapshot/list")

    async def snapshot_create(self, description: str = "") -> dict:
        return await self._call("snapshot/create", description=description)

    async def snapshot_delete(self, file_name: str) -> dict:
        return await self._call("snapshot/delete", fileName=file_name)

    async def snapshot_restore(self, file_name: str) -> dict:
        return await self._call("snapshot/restore", fileName=file_name)
