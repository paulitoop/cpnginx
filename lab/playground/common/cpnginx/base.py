"""Base functionality for cpnginx server and client."""

import base64
import io
import os
import re
import subprocess
import tarfile
import zipfile
from pathlib import Path
from common.logging import AppLogger

from .config import (
    CPNGINX_BIN,
    CERTMGR_BIN,
    CPCONFIG_BIN,
    CPNGINX_USER,
    CPNGINX_CONF_PATH,
    CPNGINX_DEFAULT_CONF_PATH,
    CPNGINX_TEMPLATE_PATH,
    CPNGINX_DEFAULT_TEMPLATE_PATH,
    CA_CERT_DIR,
)

# Module-level logger
logger = AppLogger(__name__)


def _safe_member_name(name: str) -> str:
    """Return only the file name to avoid archive path traversal."""
    return Path(name).name


def _decode_base64_payload(value: str) -> bytes:
    """Decode a base64 payload that may contain line breaks."""
    normalized = "".join(value.split())
    return base64.b64decode(normalized)


def _write_pfx_from_zip(payload: bytes, pfx_name: str, target_dir: str) -> str | None:
    """Extract a PFX file from a ZIP payload."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for member in archive.infolist():
            member_name = _safe_member_name(member.filename)
            if not member_name.endswith(".pfx"):
                continue
            if pfx_name and member_name != pfx_name:
                continue

            target_path = Path(target_dir) / (pfx_name or member_name)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(archive.read(member))
            return str(target_path)
    return None


def _write_pfx_from_tar(payload: bytes, pfx_name: str, target_dir: str) -> str | None:
    """Extract a PFX file from a TAR/TAR.GZ payload."""
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:*") as archive:
        for member in archive.getmembers():
            member_name = _safe_member_name(member.name)
            if not member.isfile() or not member_name.endswith(".pfx"):
                continue
            if pfx_name and member_name != pfx_name:
                continue

            extracted = archive.extractfile(member)
            if extracted is None:
                continue

            target_path = Path(target_dir) / (pfx_name or member_name)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(extracted.read())
            return str(target_path)
    return None


def ensure_pfx_file(base_path: str, pfx_name: str) -> str | None:
    """Ensure the PFX exists, optionally restoring it from base64 archive env vars."""
    pfx_path = os.path.join(base_path, pfx_name)
    if os.path.exists(pfx_path):
        return pfx_path

    zip_payload = os.getenv("CONTAINER_ZIP_BASE64", "")
    tar_payload = os.getenv("CONTAINER_TAR_BASE64", "")

    if zip_payload.strip():
        logger.info("PFX file not found, trying CONTAINER_ZIP_BASE64", path=pfx_path)
        restored = _write_pfx_from_zip(_decode_base64_payload(zip_payload), pfx_name, base_path)
        if restored:
            return restored

    if tar_payload.strip():
        logger.info("PFX file not found, trying CONTAINER_TAR_BASE64", path=pfx_path)
        restored = _write_pfx_from_tar(_decode_base64_payload(tar_payload), pfx_name, base_path)
        if restored:
            return restored

    return None


class PfxInstaller:
    """Installs PFX certificates using certmgr."""

    def __init__(self, pfx_path: str, pin: str, username: str = CPNGINX_USER):
        self.pfx_path = pfx_path
        self.pin = pin
        self.username = username

        self.keyid = None
        self.serial = None
        self.last_stdout = ""
        self.last_stderr = ""

    def ensure_installed(self) -> None:
        """Ensure PFX certificate is installed."""
        logger.info("Checking PFX certificate", path=self.pfx_path)
        self.check_pfx()

        logger.info("Installing PFX certificate")
        self.install_pfx()

        logger.info("Re-checking PFX after installation")
        self.check_pfx()

        logger.info("PFX installation completed", keyid=self.keyid, serial=self.serial)

    def _run_certmgr(self, args: list[str]) -> subprocess.CompletedProcess:
        """Run certmgr command"""
        cmd = [CERTMGR_BIN, *args]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        self.last_stdout = result.stdout or ""
        self.last_stderr = result.stderr or ""

        logger.debug("certmgr executed", exit_code=result.returncode)

        if result.returncode != 0:
            logger.error(
                "certmgr command failed",
                exit_code=result.returncode,
                stderr=self.last_stderr
            )
            raise RuntimeError(
                f"certmgr failed with exit code {result.returncode}\n"
                f"stdout:\n{self.last_stdout}\n"
                f"stderr:\n{self.last_stderr}"
            )

        return result

    def install_pfx(self) -> None:
        """Install PFX certificate."""
        args = [
            "-inst",
            "-provtype", "24",
            "-pfx",
            "-pin", self.pin,
            "-file", self.pfx_path,
            "-newpin", "",
        ]
        self._run_certmgr(args)

    def check_pfx(self) -> None:
        """Check PFX certificate and parse output."""
        args = [
            "-list",
            "-provtype", "24",
            "-pfx",
            "-pin", self.pin,
            "-file", self.pfx_path,
        ]
        self._run_certmgr(args)
        self._parse_certmgr_output(self.last_stdout)

    def _parse_certmgr_output(self, output: str) -> None:
        """Parse certmgr output to extract keyid and serial."""
        keyid_match = re.search(r"SubjectKeyID\s*:\s*(.+)", output, re.IGNORECASE)
        if keyid_match:
            self.keyid = keyid_match.group(1).strip()

        serial_match = re.search(r"Serial\s*:\s*(.+)", output, re.IGNORECASE)
        if serial_match:
            self.serial = serial_match.group(1).strip()


class Configurator:
    """Renders nginx configuration from template."""

    def __init__(self, serial: str):
        self.serial = serial

    def render_template(self, template_path: str, output_path: str) -> None:
        """Render configuration template with certificate serial."""
        logger.info("Rendering configuration template", template=template_path, output=output_path)
        template = Path(template_path).read_text(encoding="utf-8")
        config = template.replace("{{ cert_serial }}", self.serial)

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(config, encoding="utf-8")

        logger.info("Configuration rendered successfully", path=output_path)


def license_installer(license_key: str | None) -> None:
    """Install CSP license key if provided."""
    if license_key is None or not str(license_key).strip():
        logger.info("CSP license is not provided, skipping installation")
        return

    license_key = str(license_key).strip()

    logger.info("Installing CSP license")
    args = ["-license", "-setlocal", license_key]
    cmd = [CPCONFIG_BIN, *args]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        logger.error(
            "cpconfig license installation failed",
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
        raise RuntimeError(
            f"cpconfig failed with exit code {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    logger.info("CSP license installed successfully")


def install_ca_certs() -> None:
    """Install CA certificates from CA_CERT_DIR."""
    try:
        logger.info("Installing CA certificates from directory", path=CA_CERT_DIR)
        for cert_file in Path(CA_CERT_DIR).glob("*.cer"):
            logger.info("Installing CA certificate", cert=str(cert_file))
            args = [
                "-inst",
                "-store", "uRoot",
                "-file", str(cert_file),
            ]
            cmd = [CERTMGR_BIN, *args]
            result = subprocess.run(
                cmd,
                input="o\n",
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                logger.error(
                    "Failed to install CA certificate",
                    cert=str(cert_file),
                    exit_code=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )
                raise RuntimeError(
                    f"certmgr failed with exit code {result.returncode}\n"
                    f"stdout:\n{result.stdout}\n"
                    f"stderr:\n{result.stderr}"
                )
        logger.info("All CA certificates installed successfully")
    except Exception as e:
        logger.exception("Error installing CA certificates", error=str(e))
        raise


def start_cpnginx() -> int:
    """Main entry point for cpnginx server/client."""
    try:
        base_path = "/app/keys"
        pfx_name = os.getenv("PFX_NAME")
        pfx_pin = os.getenv("PFX_PIN")
        csp_license = os.getenv("CSP_LICENSE")

        if not pfx_name or not pfx_pin:
            logger.error("PFX_NAME or PFX_PIN environment variable is not set")
            return 1

        pfx_path = ensure_pfx_file(base_path, pfx_name)
        if not pfx_path:
            logger.error("PFX file not found", path=pfx_path)
            return 1

        license_installer(csp_license)

        installer = PfxInstaller(pfx_path=pfx_path, pin=pfx_pin)
        installer.ensure_installed()

        if not installer.serial:
            logger.error("Certificate serial was not extracted from PFX")
            return 1

        configurator = Configurator(serial=installer.serial)
        configurator.render_template(
            template_path=CPNGINX_DEFAULT_TEMPLATE_PATH,
            output_path=CPNGINX_DEFAULT_CONF_PATH,
        )
        configurator.render_template(
            template_path=CPNGINX_TEMPLATE_PATH,
            output_path=CPNGINX_CONF_PATH,
        )
        install_ca_certs()
        logger.info("Starting cpnginx daemon")
        os.execv(
            CPNGINX_BIN,
            [CPNGINX_BIN, "-g", "daemon off;"]
        )

    except Exception as e:
        logger.exception("Unexpected error during startup", error=str(e))
        return 1
