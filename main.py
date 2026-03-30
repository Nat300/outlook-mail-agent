import msal,os,requests,anthropic
from dotenv import load_dotenv

load_dotenv()

# Your app's credentials from the Azure portal
CLIENT_ID = os.getenv("CLIENT_ID")
TENANT_ID = "consumers"

# What permissions we're requesting
SCOPES = ["Mail.Read", "Mail.ReadWrite"]

def get_access_token():
    # Set up a local token cache file
    cache = msal.SerializableTokenCache()
    cache_file = ".token_cache"

    # Load existing cache if it exists
    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            cache.deserialize(f.read())

    # Create an MSAL app instance
    app = msal.PublicClientApplication(
        client_id=CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        token_cache=cache
    )

    # Check if we already have a valid token in cache
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            print("Using cached token")
            # Save updated cache
            with open(cache_file, "w") as f:
                f.write(cache.serialize())
            return result["access_token"]

    # No valid cache — do the full device flow login
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise Exception("Failed to create device flow")

    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" in result:
        print("Authentication successful!")
        # Save the token to cache for next time
        with open(cache_file, "w") as f:
            f.write(cache.serialize())
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
        return emails
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return []

        


def classify_email(client, email):
    # Extract the relevant fields from the email
    sender = email['from']['emailAddress']['address']
    subject = email['subject']
    preview = email['bodyPreview'][:300]

    # Build the prompt
    prompt = f"""You are an email classifier. Classify the following email into exactly one of these categories:
- SPAM
- NEWSLETTER
- ACTION_REQUIRED 
- IMPORTANT
- ALERTS
- OTHER

Email:
From: {sender}
Subject: {subject}
Preview: {preview}

Respond with only the category name, nothing else."""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    return message.content[0].text.strip()



# Initialize the Anthropic client
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Get token and fetch emails
token = get_access_token()
emails = get_emails(token)

# Classify each email
for email in emails:
    category = classify_email(client, email)
    print(f"\nSubject: {email['subject']}")
    print(f"Category: {category}")
