import pytest

from app.network_scanner import parse_nmap_xml, parse_up_hosts, validate_private_target


def test_validate_private_target():
    assert validate_private_target("192.168.10.0/24") == "192.168.10.0/24"
    assert validate_private_target("10.0.0.5/32") == "10.0.0.5/32"
    with pytest.raises(ValueError):
        validate_private_target("8.8.8.0/24")
    with pytest.raises(ValueError):
        validate_private_target("10.0.0.0/16")
    with pytest.raises(ValueError):
        validate_private_target("192.168.1.12/24")


def test_parse_nmap_xml_builds_services_and_recommendations():
    xml = """<?xml version="1.0"?>
    <nmaprun>
      <host>
        <status state="up"/>
        <address addr="192.168.1.10" addrtype="ipv4"/>
        <hostnames><hostname name="serveur-pme"/></hostnames>
        <ports>
          <port protocol="tcp" portid="22">
            <state state="open"/>
            <service name="ssh" product="OpenSSH" version="9.6"/>
          </port>
          <port protocol="tcp" portid="443">
            <state state="open"/>
            <service name="https"/>
          </port>
        </ports>
      </host>
    </nmaprun>"""
    hosts = parse_nmap_xml(xml)
    assert hosts[0]["ip_address"] == "192.168.1.10"
    assert hosts[0]["hostname"] == "serveur-pme"
    assert [port["port"] for port in hosts[0]["ports"]] == [22, 443]
    assert len(hosts[0]["recommendations"]) == 2


def test_parse_up_hosts_excludes_network_and_broadcast_addresses():
    xml = """<?xml version="1.0"?>
    <nmaprun>
      <host><status state="up"/><address addr="192.168.1.0" addrtype="ipv4"/></host>
      <host><status state="up"/><address addr="192.168.1.1" addrtype="ipv4"/></host>
      <host><status state="down"/><address addr="192.168.1.2" addrtype="ipv4"/></host>
      <host><status state="up"/><address addr="192.168.1.255" addrtype="ipv4"/></host>
    </nmaprun>"""
    assert parse_up_hosts(xml, "192.168.1.0/24") == ["192.168.1.1"]
