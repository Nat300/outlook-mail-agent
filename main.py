import msal,os,requests
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


def get_emails(token):
    # The Microsoft Graph API endpoint for inbox messages
    url = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
    
    # We pass the token in the request header to prove we're authenticated
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Only fetch 10 emails for now, and only the fields we need
    params = {
        "$top": 10,
        "$select": "subject,from,receivedDateTime,bodyPreview"
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        emails = response.json()["value"]
        print(f"Fetched {len(emails)} emails")
        for email in emails:
            print(f"\nFrom: {email['from']['emailAddress']['address']}")
            print(f"Subject: {email['subject']}")
            print(f"Preview: {email['bodyPreview'][:100]}")
    else:
        print(f"Error: {response.status_code} - {response.text}")


token = get_access_token()
get_emails(token)