import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))
import pyotp
from SmartApi.smartConnect import SmartConnect

api_key = os.getenv('ANGELONE_API_KEY')
client_id = os.getenv('ANGELONE_CLIENT_ID')
password = os.getenv('ANGELONE_API_SECRET')
totp_secret = os.getenv('ANGELONE_TOTP_SECRET')

if not all([api_key, client_id, password, totp_secret]):
    print("ERROR: One or more required environment variables are missing.")
    print(f"ANGELONE_API_KEY: {api_key}")
    print(f"ANGELONE_CLIENT_ID: {client_id}")
    print(f"ANGELONE_API_SECRET: {'*' * len(password) if password else None}")
    print(f"ANGELONE_TOTP_SECRET: {totp_secret}")
    exit(1)

totp = pyotp.TOTP(totp_secret).now()

print(f"API Key: {api_key}")
print(f"Client ID: {client_id}")
print(f"Password: {'*' * len(password) if password else None}")
print(f"TOTP: {totp}")

api = SmartConnect(api_key=api_key)
try:
    data = api.generateSession(clientCode=client_id, password=password, totp=totp)
    print("Login response:")
    print(data)
except Exception as e:
    print(f"Login exception: {e}")
