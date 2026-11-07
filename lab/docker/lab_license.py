"""Install an explicitly supplied local license without logging its value."""
import subprocess


def install_license(value):
    try:
        result = subprocess.run(
            ['/opt/cprocsp/sbin/amd64/cpconfig', '-license', '-set', value],
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError('CryptoPro license installation timed out; value is hidden') from None
    if result.returncode:
        output = (result.stdout + result.stderr).lower()
        if 'expired or not yet valid' in output:
            raise RuntimeError('The supplied CryptoPro license is expired or not yet valid; provide a current TLS Server license')
        # The CLI may echo its input on failure. Never forward its raw output.
        raise RuntimeError('The supplied CryptoPro TLS server license was not accepted; value is hidden')
