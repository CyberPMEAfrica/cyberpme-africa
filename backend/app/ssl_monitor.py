from datetime import datetime, timezone
from ipaddress import ip_address
import re
import socket
import ssl

from cryptography import x509
from cryptography.x509.oid import NameOID


ALLOWED_TLS_PORTS = {443, 8443}
DOMAIN_PATTERN = re.compile(
    r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)


def validate_public_hostname(hostname: str, port: int) -> tuple[str, list[str]]:
    normalized = hostname.strip().lower().rstrip(".")
    if port not in ALLOWED_TLS_PORTS:
        raise ValueError("Seuls les ports TLS 443 et 8443 sont autorisés.")
    try:
        ip_address(normalized)
    except ValueError:
        pass
    else:
        raise ValueError("Saisissez un nom de domaine public, pas une adresse IP.")
    if not DOMAIN_PATTERN.fullmatch(normalized):
        raise ValueError("Saisissez un nom de domaine valide, par exemple example.com.")
    try:
        resolved = sorted({item[4][0] for item in socket.getaddrinfo(normalized, port, type=socket.SOCK_STREAM)})
    except socket.gaierror as exc:
        raise ValueError("Le nom de domaine ne peut pas être résolu.") from exc
    if not resolved:
        raise ValueError("Le nom de domaine ne renvoie aucune adresse.")
    if any(not ip_address(address).is_global for address in resolved):
        raise ValueError("Le domaine doit résoudre uniquement vers des adresses IP publiques.")
    return normalized, resolved


def name_value(name: x509.Name, oid: x509.ObjectIdentifier) -> str | None:
    attributes = name.get_attributes_for_oid(oid)
    return attributes[0].value if attributes else None


def inspect_certificate(hostname: str, port: int) -> dict:
    now = datetime.now(timezone.utc)
    unverified_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    unverified_context.check_hostname = False
    unverified_context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((hostname, port), timeout=10) as raw_socket:
        with unverified_context.wrap_socket(raw_socket, server_hostname=hostname) as tls_socket:
            certificate = x509.load_der_x509_certificate(tls_socket.getpeercert(binary_form=True))
            tls_version = tls_socket.version()
            selected_cipher = tls_socket.cipher()

    valid_from = certificate.not_valid_before_utc
    expires_at = certificate.not_valid_after_utc
    days_remaining = int((expires_at - now).total_seconds() // 86400)
    chain_valid = True
    verification_error = None
    try:
        verified_context = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=10) as raw_socket:
            with verified_context.wrap_socket(raw_socket, server_hostname=hostname):
                pass
    except ssl.SSLCertVerificationError as exc:
        chain_valid = False
        verification_error = exc.verify_message

    if expires_at <= now:
        status = "expired"
    elif not chain_valid:
        status = "critical"
    elif days_remaining <= 30:
        status = "warning"
    else:
        status = "valid"

    common_name = name_value(certificate.subject, NameOID.COMMON_NAME)
    issuer_name = name_value(certificate.issuer, NameOID.ORGANIZATION_NAME) or name_value(certificate.issuer, NameOID.COMMON_NAME)
    return {
        "status": status,
        "subject": common_name,
        "issuer": issuer_name,
        "valid_from": valid_from,
        "expires_at": expires_at,
        "days_remaining": days_remaining,
        "chain_valid": chain_valid,
        "tls_version": tls_version,
        "cipher": selected_cipher[0] if selected_cipher else None,
        "error": verification_error,
    }
