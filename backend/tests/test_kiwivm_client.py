import httpx
import pytest

from app.kiwivm.client import KiwiVMClient, KiwiVMError


def client_with(handler) -> KiwiVMClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return KiwiVMClient("1234567", "private-xyz", http=http)


async def test_success_passes_credentials_and_returns_body():
    seen = {}

    def handler(request):
        seen.update({k: v for k, v in request.url.params.items()})
        return httpx.Response(200, json={"ve_status": "running"})

    c = client_with(handler)
    data = await c.get_live_service_info()
    await c.aclose()
    assert data == {"ve_status": "running"}
    assert seen["veid"] == "1234567"
    assert seen["api_key"] == "private-xyz"


async def test_api_error_raises_kiwivm_error_with_code():
    def handler(request):
        return httpx.Response(200, json={"error": 7, "message": "invalid veid"})

    c = client_with(handler)
    with pytest.raises(KiwiVMError) as ei:
        await c.get_live_service_info()
    await c.aclose()
    assert ei.value.code == 7
    assert ei.value.message == "invalid veid"


async def test_network_error_retries_once_then_raises():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        raise httpx.ConnectError("boom")

    c = client_with(handler)
    with pytest.raises(KiwiVMError) as ei:
        await c.get_live_service_info()
    await c.aclose()
    assert calls["n"] == 2  # 重试 1 次后放弃
    assert ei.value.code == -1


async def test_network_error_retry_can_succeed():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json={"remaining_points_15min": 100})

    c = client_with(handler)
    data = await c.get_rate_limit_status()
    await c.aclose()
    assert data == {"remaining_points_15min": 100}
    assert calls["n"] == 2


async def test_http_error_not_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(502, text="<html>gateway error</html>")

    c = client_with(handler)
    with pytest.raises(KiwiVMError) as ei:
        await c.get_live_service_info()
    await c.aclose()
    assert calls["n"] == 1          # HTTP 错误不重试
    assert ei.value.code == -1
    assert "502" in ei.value.message


async def test_error_zero_is_success():
    def handler(request):
        return httpx.Response(200, json={"error": 0, "ve_status": "running"})

    c = client_with(handler)
    data = await c.get_live_service_info()
    await c.aclose()
    assert data["ve_status"] == "running"


async def test_power_calls_action_endpoint():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url.path)
        seen.update({k: v for k, v in request.url.params.items()})
        return httpx.Response(200, json={})

    c = client_with(handler)
    await c.power("kill")
    await c.aclose()
    assert seen["url"] == "/v1/kill"
    assert seen["veid"] == "1234567"            # 凭据仍然注入
    assert seen["api_key"] == "private-xyz"


async def test_snapshot_create_sends_description():
    seen = {}

    def handler(request):
        seen.update({k: v for k, v in request.url.params.items()})
        return httpx.Response(200, json={"fileName": "snapshot-001"})

    c = client_with(handler)
    data = await c.snapshot_create("before-upgrade")
    await c.aclose()
    assert data == {"fileName": "snapshot-001"}
    assert seen["description"] == "before-upgrade"


async def test_snapshot_delete_and_restore_send_file_name():
    urls = []

    def handler(request):
        urls.append((str(request.url.path), dict(request.url.params)))
        return httpx.Response(200, json={})

    c = client_with(handler)
    await c.snapshot_delete("snapshot-001")
    await c.snapshot_restore("snapshot-001")
    await c.aclose()
    assert urls[0][0] == "/v1/snapshot/delete"
    assert urls[0][1]["fileName"] == "snapshot-001"
    assert urls[1][0] == "/v1/snapshot/restore"
    assert urls[1][1]["fileName"] == "snapshot-001"


async def test_snapshot_list_returns_body():
    seen = {}
    body = {"snapshots": [{"fileName": "snapshot-001", "timestamp": 1690000000,
                           "status": "complete", "description": "", "size": 1024}]}

    def handler(request):
        seen["url"] = str(request.url.path)
        return httpx.Response(200, json=body)

    c = client_with(handler)
    data = await c.snapshot_list()
    await c.aclose()
    assert seen["url"] == "/v1/snapshot/list"
    assert data == body
