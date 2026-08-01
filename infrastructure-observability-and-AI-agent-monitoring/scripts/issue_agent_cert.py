#!/usr/bin/env python3
"""Create an internal CA and mTLS client certificates for SDK agents.

Run this only from a protected operator workstation. It refuses to overwrite
existing key material unless --force is passed explicitly.
"""

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def write_private_key(path: Path, key, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {path}; pass --force if intentional")
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )


def write_certificate(path: Path, certificate: x509.Certificate, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {path}; pass --force if intentional")
    path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", action="append", required=True, help="Agent CN; repeat as needed")
    parser.add_argument("--out-dir", default="deploy/certs", help="Protected certificate output directory")
    parser.add_argument("--force", action="store_true", help="Allow replacement of existing material")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    ca_subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "agent-observability-agent-ca")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_subject)
        .issuer_name(ca_subject)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True,
            crl_sign=True, encipher_only=False, decipher_only=False,
        ), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    write_private_key(out_dir / "agent-ca-key.pem", ca_key, args.force)
    write_certificate(out_dir / "agent-ca.pem", ca_cert, args.force)

    for agent in sorted(set(args.agent)):
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, agent)]))
            .issuer_name(ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256())
        )
        write_private_key(out_dir / f"{agent}-key.pem", key, args.force)
        write_certificate(out_dir / f"{agent}.pem", cert, args.force)


if __name__ == "__main__":
    main()
