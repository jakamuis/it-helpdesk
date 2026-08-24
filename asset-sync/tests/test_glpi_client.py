import httpx
import pytest

from app.services.glpi_client import GLPIClient, GLPIClientError


def authenticated_client() -> GLPIClient:
    client = GLPIClient()
    client.session_token = "test-session"
    client.headers["Session-Token"] = "test-session"
    return client


@pytest.mark.asyncio
async def test_qr_search_filters_exact_match_and_scopes_entity(httpx_mock):
    observed = {}

    def search_response(request: httpx.Request):
        observed["path"] = request.url.path
        observed["params"] = request.url.params
        return httpx.Response(
            200,
            json={
                "data": [
                    {"2": 10, "6": "QR-10-old"},
                    {"2": 11, "6": " qr-10 "},
                ]
            },
        )

    httpx_mock.add_callback(search_response)
    client = authenticated_client()

    result = await client.search_asset_by_qrcode("QR-10", itemtype="Computer", entities_id=7)

    assert result == {"id": 11, "qrcode": " qr-10 "}
    assert observed["path"].endswith("/search/Computer")
    params = observed["params"]
    assert params["criteria[0][field]"] == "6"
    assert params["criteria[0][searchtype]"] == "equals"
    assert params["criteria[0][value]"] == "QR-10"
    assert params["criteria[1][field]"] == "80"
    assert params["criteria[1][value]"] == "7"
    assert params["forcedisplay[0]"] == "2"
    assert params["forcedisplay[1]"] == "6"


@pytest.mark.asyncio
async def test_qr_search_fails_closed_on_duplicate_exact_matches(httpx_mock):
    httpx_mock.add_response(
        json={"data": [{"2": 1, "6": "DUP-1"}, {"2": 2, "6": "dup-1"}]}
    )
    client = authenticated_client()

    with pytest.raises(GLPIClientError, match="Duplicate QRCODE UNIT"):
        await client.search_asset_by_qrcode("DUP-1", itemtype="Monitor", entities_id=0)


@pytest.mark.asyncio
async def test_qr_search_fails_closed_on_unverifiable_or_partial_results(httpx_mock):
    client = authenticated_client()
    httpx_mock.add_response(status_code=200, json={"data": [{"2": 9}]})

    with pytest.raises(GLPIClientError, match="unverifiable"):
        await client.search_asset_by_qrcode("QR-MISSING-FIELD", itemtype="Computer")

    httpx_mock.add_response(
        status_code=206,
        headers={"Content-Range": "0-49/60"},
        json={"data": [{"2": 10, "6": "QR-PARTIAL"}]},
    )
    with pytest.raises(GLPIClientError, match="partial"):
        await client.search_asset_by_qrcode("QR-PARTIAL", itemtype="Computer")


@pytest.mark.asyncio
async def test_qr_search_rejects_unsupported_itemtype_without_http():
    client = authenticated_client()

    with pytest.raises(GLPIClientError, match="Unsupported"):
        await client.search_asset_by_qrcode("P-1", itemtype="Printer")


@pytest.mark.asyncio
async def test_init_session_transport_error_is_not_retried(httpx_mock):
    attempts = 0

    def fail_after_send(request: httpx.Request):
        nonlocal attempts
        attempts += 1
        raise httpx.ReadError("response was lost", request=request)

    httpx_mock.add_callback(fail_after_send)
    client = GLPIClient()

    with pytest.raises(httpx.ReadError, match="response was lost"):
        await client._init_session()

    assert attempts == 1


@pytest.mark.asyncio
async def test_kill_session_always_removes_stale_header(httpx_mock):
    httpx_mock.add_response(status_code=200, json={})
    client = authenticated_client()

    await client.kill_session()

    assert client.session_token is None
    assert "Session-Token" not in client.headers


@pytest.mark.asyncio
async def test_create_transport_error_is_not_retried(httpx_mock):
    attempts = 0

    def fail_after_send(request: httpx.Request):
        nonlocal attempts
        attempts += 1
        raise httpx.ReadError("response was lost", request=request)

    httpx_mock.add_callback(fail_after_send)
    client = authenticated_client()

    with pytest.raises(httpx.ReadError, match="response was lost"):
        await client.create_asset({"otherserial": "QR-ONCE"}, itemtype="Computer")

    assert attempts == 1


@pytest.mark.asyncio
async def test_infocom_create_transport_error_is_not_retried(httpx_mock):
    attempts = 0

    def fail_after_send(request: httpx.Request):
        nonlocal attempts
        attempts += 1
        raise httpx.ReadError("response was lost", request=request)

    httpx_mock.add_callback(fail_after_send)
    client = authenticated_client()

    with pytest.raises(httpx.ReadError, match="response was lost"):
        await client.create_infocom({"itemtype": "Computer", "items_id": 10, "value": 1})

    assert attempts == 1


@pytest.mark.asyncio
async def test_dropdown_and_infocom_search_fail_closed_on_ambiguity(httpx_mock):
    client = authenticated_client()
    httpx_mock.add_response(
        status_code=200,
        json={"data": [{"2": 1, "1": "Dell"}, {"2": 2, "1": "dell"}]},
    )
    with pytest.raises(GLPIClientError, match="Ambiguous dropdown"):
        await client.find_dropdown("Manufacturer", "Dell")

    httpx_mock.add_response(
        status_code=200,
        json={"data": [{"2": 7}, {"2": 8}]},
    )
    with pytest.raises(GLPIClientError, match="Duplicate Infocom"):
        await client.search_infocom("Computer", 10)


@pytest.mark.asyncio
async def test_dropdown_search_rejects_partial_results(httpx_mock):
    httpx_mock.add_response(
        status_code=206,
        headers={"Content-Range": "0-49/60"},
        json={"data": [{"2": 1, "1": "Dell"}]},
    )
    client = authenticated_client()

    with pytest.raises(GLPIClientError, match="partial"):
        await client.find_dropdown("Manufacturer", "Dell")


@pytest.mark.asyncio
async def test_infocom_search_forces_owner_fields_and_verifies_detail(httpx_mock):
    httpx_mock.add_response(status_code=200, json={"data": [{"2": 7}]})
    httpx_mock.add_response(
        status_code=200,
        json={"id": 7, "itemtype": "Monitor", "items_id": 10, "value": 100.0},
    )
    client = authenticated_client()

    result = await client.search_infocom("Monitor", 10)

    assert result == 7
    search_request = httpx_mock.get_requests()[0]
    assert search_request.url.params["forcedisplay[0]"] == "2"
    assert search_request.url.params["forcedisplay[1]"] == "20"
    assert search_request.url.params["forcedisplay[2]"] == "21"
    assert httpx_mock.get_requests()[1].url.path.endswith("/Infocom/7")


@pytest.mark.asyncio
async def test_infocom_search_rejects_partial_or_wrong_owner(httpx_mock):
    client = authenticated_client()
    httpx_mock.add_response(
        status_code=206,
        headers={"Content-Range": "0-49/60"},
        json={"data": [{"2": 7}]},
    )
    with pytest.raises(GLPIClientError, match="partial"):
        await client.search_infocom("Computer", 10)

    httpx_mock.add_response(status_code=200, json={"data": [{"2": 7}]})
    httpx_mock.add_response(
        status_code=200,
        json={"id": 7, "itemtype": "Computer", "items_id": 11},
    )
    with pytest.raises(GLPIClientError, match="ownership"):
        await client.search_infocom("Computer", 10)


@pytest.mark.asyncio
async def test_infocom_search_rejects_unverifiable_rows(httpx_mock):
    httpx_mock.add_response(status_code=200, json={"data": [{"20": "Computer"}]})
    client = authenticated_client()

    with pytest.raises(GLPIClientError, match="unverifiable"):
        await client.search_infocom("Computer", 10)


@pytest.mark.asyncio
async def test_dat_resolver_uses_verified_option_12_and_exact_owner_detail(httpx_mock):
    httpx_mock.add_response(
        status_code=200,
        json={"data": [{"2": 17, "12": " DAT-01 ", "20": "Computer", "21": 10}]},
    )
    httpx_mock.add_response(
        status_code=200,
        json={
            "id": 17,
            "immo_number": "dat-01",
            "itemtype": "Computer",
            "items_id": 10,
        },
    )
    client = authenticated_client()

    owner = await client.resolve_infocom_by_dat("DAT-01")

    assert owner["id"] == 17
    assert owner["itemtype"] == "Computer"
    assert owner["items_id"] == 10
    search_request = httpx_mock.get_requests()[0]
    assert search_request.url.params["criteria[0][field]"] == "12"
    assert search_request.url.params["criteria[0][searchtype]"] == "equals"
    assert search_request.url.params["forcedisplay[1]"] == "12"
    assert search_request.url.params["is_recursive"] == "true"


@pytest.mark.asyncio
async def test_dat_resolver_rejects_partial_duplicate_and_unverifiable_results(httpx_mock):
    client = authenticated_client()
    httpx_mock.add_response(
        status_code=206,
        headers={"Content-Range": "0-49/60"},
        json={"data": [{"2": 1, "12": "DAT-1"}]},
    )
    with pytest.raises(GLPIClientError, match="partial"):
        await client.resolve_infocom_by_dat("DAT-1")

    httpx_mock.add_response(
        status_code=200,
        json={"data": [{"2": 1, "12": "DAT-1"}, {"2": 2, "12": "dat-1"}]},
    )
    with pytest.raises(GLPIClientError, match="Duplicate DAT"):
        await client.resolve_infocom_by_dat("DAT-1")

    httpx_mock.add_response(status_code=200, json={"data": [{"2": 1}]})
    with pytest.raises(GLPIClientError, match="unverifiable"):
        await client.resolve_infocom_by_dat("DAT-1")


@pytest.mark.asyncio
async def test_dat_resolver_rejects_detail_that_does_not_confirm_exact_dat(httpx_mock):
    httpx_mock.add_response(status_code=200, json={"data": [{"2": 17, "12": "DAT-1"}]})
    httpx_mock.add_response(
        status_code=200,
        json={"id": 17, "immo_number": "DAT-2", "itemtype": "Computer", "items_id": 10},
    )
    client = authenticated_client()

    with pytest.raises(GLPIClientError, match="could not be verified"):
        await client.resolve_infocom_by_dat("DAT-1")


@pytest.mark.asyncio
async def test_identity_resolver_returns_verified_record_across_all_supported_types(httpx_mock):
    httpx_mock.add_response(
        status_code=200,
        json={"data": [{"2": 41, "6": " qr-41 "}]},
    )
    httpx_mock.add_response(
        status_code=200,
        json={"id": 41, "otherserial": " QR-41 ", "entities_id": 7, "name": "Laptop"},
    )
    httpx_mock.add_response(status_code=200, json={"data": []})
    client = authenticated_client()

    identity = await client.resolve_asset_identity(
        "QR-41",
        expected_itemtype="Computer",
        expected_entities_id=7,
    )

    assert identity == {
        "id": 41,
        "qrcode": "QR-41",
        "itemtype": "Computer",
        "entities_id": 7,
        "record": {
            "id": 41,
            "otherserial": " QR-41 ",
            "entities_id": 7,
            "name": "Laptop",
        },
    }
    search_requests = [
        request for request in httpx_mock.get_requests() if "/search/" in request.url.path
    ]
    assert [request.url.path.rsplit("/", 1)[-1] for request in search_requests] == [
        "Computer",
        "Monitor",
    ]
    assert all(request.url.params["is_recursive"] == "true" for request in search_requests)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("expected_itemtype", "expected_entity", "responses", "message"),
    [
        (
            "Computer",
            7,
            [
                {"data": []},
                {"data": [{"2": 51, "6": "QR-X"}]},
                {"id": 51, "otherserial": "QR-X", "entities_id": 7},
            ],
            "different GLPI asset type",
        ),
        (
            "Computer",
            7,
            [
                {"data": [{"2": 52, "6": "QR-X"}]},
                {"id": 52, "otherserial": "QR-X", "entities_id": 8},
                {"data": []},
            ],
            "different GLPI entity",
        ),
    ],
)
async def test_identity_resolver_blocks_cross_type_or_entity_collision(
    httpx_mock,
    expected_itemtype,
    expected_entity,
    responses,
    message,
):
    for response in responses:
        httpx_mock.add_response(status_code=200, json=response)
    client = authenticated_client()

    with pytest.raises(GLPIClientError, match=message):
        await client.resolve_asset_identity(
            "QR-X",
            expected_itemtype=expected_itemtype,
            expected_entities_id=expected_entity,
        )


@pytest.mark.asyncio
async def test_identity_resolver_blocks_same_qr_in_two_asset_types(httpx_mock):
    httpx_mock.add_response(status_code=200, json={"data": [{"2": 1, "6": "DUP-X"}]})
    httpx_mock.add_response(
        status_code=200,
        json={"id": 1, "otherserial": "DUP-X", "entities_id": 0},
    )
    httpx_mock.add_response(status_code=200, json={"data": [{"2": 2, "6": "dup-x"}]})
    httpx_mock.add_response(
        status_code=200,
        json={"id": 2, "otherserial": "dup-x", "entities_id": 0},
    )
    client = authenticated_client()

    with pytest.raises(GLPIClientError, match="collision"):
        await client.resolve_asset_identity(
            "DUP-X",
            expected_itemtype="Computer",
            expected_entities_id=0,
        )


@pytest.mark.asyncio
async def test_identity_resolver_fails_when_detail_cannot_verify_identity(httpx_mock):
    httpx_mock.add_response(status_code=200, json={"data": [{"2": 61, "6": "QR-61"}]})
    httpx_mock.add_response(
        status_code=200,
        json={"id": 61, "otherserial": "OTHER", "entities_id": 0},
    )
    client = authenticated_client()

    with pytest.raises(GLPIClientError, match="did not confirm"):
        await client.resolve_asset_identity(
            "QR-61",
            expected_itemtype="Computer",
            expected_entities_id=0,
        )
