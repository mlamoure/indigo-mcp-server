"""
SSL/TLS certificate manager for MCP server HTTPS support.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa


class CertManager:
    """Manages SSL/TLS certificate generation and validation for MCP server."""
    
    def __init__(self, cert_dir: str, logger: Optional[logging.Logger] = None):
        """
        Initialize the certificate manager.
        
        Args:
            cert_dir: Directory to store certificates
            logger: Optional logger instance
        """
        self.cert_dir = cert_dir
        self.logger = logger or logging.getLogger("Plugin")
        self.cert_file = os.path.join(cert_dir, "cert.pem")
        self.key_file = os.path.join(cert_dir, "key.pem")
        
        # Ensure certificate directory exists
        os.makedirs(cert_dir, exist_ok=True)
    
    def generate_self_signed_cert(self, 
                                 common_name: str = "localhost",
                                 validity_days: int = 365) -> Tuple[str, str]:
        """
        Generate a self-signed SSL certificate and private key.
        
        Args:
            common_name: Common name for the certificate
            validity_days: Certificate validity period in days
            
        Returns:
            Tuple of (cert_file_path, key_file_path)
        """
        self.logger.info(f"Generating self-signed certificate for {common_name}")
        
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        
        # Create certificate
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Unknown"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Unknown"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Indigo MCP Server"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])
        
        # Create certificate builder
        cert_builder = x509.CertificateBuilder()
        cert_builder = cert_builder.subject_name(subject)
        cert_builder = cert_builder.issuer_name(issuer)
        cert_builder = cert_builder.public_key(private_key.public_key())
        cert_builder = cert_builder.serial_number(x509.random_serial_number())
        cert_builder = cert_builder.not_valid_before(datetime.utcnow())
        cert_builder = cert_builder.not_valid_after(datetime.utcnow() + timedelta(days=validity_days))
        
        # Add Subject Alternative Names for localhost and 127.0.0.1
        san_list = [
            x509.DNSName("localhost"),
            x509.IPAddress("127.0.0.1"),
        ]
        
        # Add 0.0.0.0 for remote access
        try:
            san_list.append(x509.IPAddress("0.0.0.0"))
        except Exception:
            pass  # Skip if IP address is invalid
        
        cert_builder = cert_builder.add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False
        )
        
        # Sign the certificate
        certificate = cert_builder.sign(private_key, hashes.SHA256())
        
        # Write certificate to file
        with open(self.cert_file, "wb") as f:
            f.write(certificate.public_bytes(serialization.Encoding.PEM))
        
        # Write private key to file
        with open(self.key_file, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        self.logger.info(f"Certificate generated: {self.cert_file}")
        self.logger.info(f"Private key generated: {self.key_file}")
        
        return self.cert_file, self.key_file
    
    def certificates_exist(self) -> bool:
        """
        Check if certificate files exist.
        
        Returns:
            True if both certificate and key files exist
        """
        return os.path.isfile(self.cert_file) and os.path.isfile(self.key_file)
    
    def is_certificate_valid(self) -> bool:
        """
        Check if the existing certificate is valid (not expired).
        
        Returns:
            True if certificate is valid and not expired
        """
        if not self.certificates_exist():
            return False
        
        try:
            with open(self.cert_file, "rb") as f:
                cert_data = f.read()
            
            certificate = x509.load_pem_x509_certificate(cert_data)
            
            # Check if certificate is still valid
            now = datetime.utcnow()
            return now < certificate.not_valid_after
            
        except Exception as e:
            self.logger.error(f"Error validating certificate: {e}")
            return False
    
    def get_certificate_info(self) -> Optional[dict]:
        """
        Get information about the current certificate.
        
        Returns:
            Dictionary with certificate information or None if no valid certificate
        """
        if not self.certificates_exist():
            return None
        
        try:
            with open(self.cert_file, "rb") as f:
                cert_data = f.read()
            
            certificate = x509.load_pem_x509_certificate(cert_data)
            
            return {
                "subject": certificate.subject.rfc4514_string(),
                "issuer": certificate.issuer.rfc4514_string(),
                "serial_number": certificate.serial_number,
                "not_valid_before": certificate.not_valid_before,
                "not_valid_after": certificate.not_valid_after,
                "is_valid": datetime.utcnow() < certificate.not_valid_after,
                "cert_file": self.cert_file,
                "key_file": self.key_file
            }
            
        except Exception as e:
            self.logger.error(f"Error reading certificate info: {e}")
            return None
    
    def ensure_certificates(self) -> Tuple[str, str]:
        """
        Ensure valid certificates exist, generating them if necessary.
        
        Returns:
            Tuple of (cert_file_path, key_file_path)
        """
        if not self.certificates_exist() or not self.is_certificate_valid():
            self.logger.info("Generating new SSL certificates")
            return self.generate_self_signed_cert()
        else:
            self.logger.debug("Using existing valid SSL certificates")
            return self.cert_file, self.key_file