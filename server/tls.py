# tls.py
"""
Self-signed X.509 certificate generator for local-network HTTPS so mobile browsers
grant navigator.mediaDevices.getUserMedia microphone permissions.
"""

from __future__ import annotations

import datetime
import ipaddress
import logging
import os
import socket
from typing import Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

logger = logging.getLogger("cave.server.tls")


def get_local_lan_ip() -> str:
    """Detect the primary local Wi-Fi/LAN IPv4 address of the Windows PC."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def ensure_local_tls_cert(cert_dir: str = "config/certs") -> Tuple[str, str]:
    """
    Generate or reuse a local X.509 self-signed certificate and private key
    including 127.0.0.1 and the current LAN IP in SubjectAlternativeName.
    """
    os.makedirs(cert_dir, exist_ok=True)
    cert_path = os.path.join(cert_dir, "cave_cert.pem")
    key_path = os.path.join(cert_dir, "cave_key.pem")

    if os.path.isfile(cert_path) and os.path.isfile(key_path):
        return cert_path, key_path

    lan_ip = get_local_lan_ip()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "CAVE Local Assistant"),
            x509.NameAttribute(NameOID.COMMON_NAME, lan_ip),
        ]
    )

    san_entries = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
    ]
    try:
        san_entries.append(x509.IPAddress(ipaddress.ip_address(lan_ip)))
    except ValueError:
        pass

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .sign(key, hashes.SHA256())
    )

    with open(key_path, "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    logger.info("Generated self-signed local HTTPS certificate for %s", lan_ip)
    return cert_path, key_path