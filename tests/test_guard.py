from sidecar.guard import allowed

def test_read_only_contract():
    assert allowed("GET", "/healthz")
    assert allowed("GET", "/v1/api/portfolio/U123/positions/0")
    assert not allowed("POST", "/v1/api/iserver/account/orders")
    assert not allowed("GET", "/v1/api/tickle")
    assert not allowed("GET", "/v1/api/portfolio/U123/positions")
