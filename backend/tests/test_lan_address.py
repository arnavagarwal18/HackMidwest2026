"""GET /lan-address: an http URL with the machine's LAN IP and the port the request came in on."""
import socket

from fastapi.testclient import TestClient

from app import lan
from app.main import app


def test_url_uses_the_mocked_lan_ip_and_the_request_port(monkeypatch):
    monkeypatch.setattr(lan, "find_lan_ip", lambda: "192.168.1.20")
    response = TestClient(app, base_url="http://localhost:8123").get("/lan-address")
    assert response.status_code == 200
    assert response.json() == {"url": "http://192.168.1.20:8123"}


def test_url_port_comes_from_the_host_header(monkeypatch):
    monkeypatch.setattr(lan, "find_lan_ip", lambda: "10.0.0.7")
    response = TestClient(app).get("/lan-address", headers={"Host": "127.0.0.1:9001"})
    assert response.json()["url"] == "http://10.0.0.7:9001"


def test_host_without_a_port_means_port_80(monkeypatch):
    monkeypatch.setattr(lan, "find_lan_ip", lambda: "10.0.0.7")
    assert TestClient(app).get("/lan-address").json()["url"] == "http://10.0.0.7:80"


def test_find_lan_ip_reads_the_socket_address_without_sending(monkeypatch):
    calls = []

    class FakeSocket:
        def __init__(self, family, kind):
            calls.append((family, kind))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def connect(self, address):
            calls.append(address)

        def getsockname(self):
            return ("192.168.5.9", 54321)

    monkeypatch.setattr(lan.socket, "socket", FakeSocket)
    assert lan.find_lan_ip() == "192.168.5.9"
    assert calls == [(socket.AF_INET, socket.SOCK_DGRAM), lan.NON_ROUTABLE_PROBE]


def test_find_lan_ip_falls_back_to_loopback_and_logs(monkeypatch, caplog):
    def no_network(*_args):
        raise OSError("Network is unreachable")

    monkeypatch.setattr(lan.socket, "socket", no_network)
    assert lan.find_lan_ip() == "127.0.0.1"
    assert "Network is unreachable" in caplog.text
