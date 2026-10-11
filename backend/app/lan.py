"""GET /lan-address: the address a phone on the same Wi-Fi can use to reach this server (for the calibration QR code)."""
import logging
import socket

from fastapi import APIRouter, Request

logger = logging.getLogger("app.lan")
router = APIRouter()

LOOPBACK = "127.0.0.1"
NON_ROUTABLE_PROBE = ("10.255.255.255", 1)
DEFAULT_HTTP_PORT = 80


def find_lan_ip() -> str:
    """This machine's LAN IPv4, or 127.0.0.1 when it has none. A UDP connect only picks a route; no packet is sent."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(NON_ROUTABLE_PROBE)
            return probe.getsockname()[0]
    except OSError as err:
        logger.warning("Could not find a LAN address (%s); answering %s instead.", err, LOOPBACK)
        return LOOPBACK


@router.get("/lan-address")
def lan_address(request: Request) -> dict:
    port = request.url.port or DEFAULT_HTTP_PORT  # the port from the Host header, as the browser sent it
    return {"url": f"http://{find_lan_ip()}:{port}"}
