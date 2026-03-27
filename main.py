import msal,os
from dotenv import load_dotenv

load_dotenv()

# Your app's credentials from the Azure portal
CLIENT_ID = os.getenv("CLIENT_ID")
TENANT_ID = "consumers"

# What permissions we're requesting
SCOPES = ["Mail.Read", "Mail.ReadWrite"]

def get_access_token():
    # Create an MSAL app instance
    app = msal.PublicClientApplication(
        client_id=CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}"
    )

    # Initiate the device code flow
    flow = app.initiate_device_flow(scopes=SCOPES)

    if "user_code" not in flow:
        raise Exception("Failed to create device flow")

    # This prints instructions telling you to go to a URL and enter a code
    print(flow["message"])

    # Wait for you to log in, then returns a token
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" in result:
        print("Authentication successful!")
        return result["access_token"]
    else:
        raise Exception(f"Authentication failed: {result.get('error_description')}")

# Run it
token = get_access_token()
print(f"Token received: {token[:20]}...")