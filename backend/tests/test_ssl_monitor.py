import socket

import pytest

from app.ssl_monitor import validate_public_hostname


def address_info(address: str, port: int):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]


def test_validate_public_hostname_accepts_public_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda hostname, port, type: address_info("93.184.216.34", port))
    hostname, addresses = validate_public_hostname("Example.COM.", 443)
    assert hostname == "example.com"
    assert addresses == ["93.184.216.34"]


def test_validate_public_hostname_rejects_private_dns_and_unsafe_inputs(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda hostname, port, type: address_info("192.168.1.20", port))
    with pytest.raises(ValueError, match="publiques"):
        validate_public_hostname("intranet.example.com", 443)
    with pytest.raises(ValueError, match="ports TLS"):
        validate_public_hostname("example.com", 444)
    with pytest.raises(ValueError, match="pas une adresse IP"):
        validate_public_hostname("8.8.8.8", 443)
