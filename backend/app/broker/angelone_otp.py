import os
import pyotp

def get_angelone_otp():
    totp_secret = os.environ.get("ANGELONE_TOTP_SECRET")
    if not totp_secret:
        raise ValueError("ANGELONE_TOTP_SECRET not set in environment")
    return pyotp.TOTP(totp_secret).now()
