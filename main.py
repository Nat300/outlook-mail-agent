import msal,os,requests,anthropic
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

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
    
    # Only fetch 50 emails for now, and only the fields we need
    params = {
        "$top": 50,
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

def delete_old_emails(token, folder_ids, categories_to_clean, weeks_old=8):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Calculate the cutoff date (8 weeks = 2 months)
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=weeks_old)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    total_deleted = 0

    for category in categories_to_clean:
        folder_id = folder_ids.get(category)
        if not folder_id:
            continue

        # Fetch emails older than the cutoff date in this folder
        url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder_id}/messages"
        params = {
            "$filter": f"receivedDateTime lt {cutoff_str} and flag/flagStatus eq 'notFlagged'",
            "$select": "id,subject,receivedDateTime",
            "$top": 50
        }

        response = requests.get(url, headers=headers, params=params)
        emails = response.json().get("value", [])

        for email in emails:
            delete_url = f"https://graph.microsoft.com/v1.0/me/messages/{email['id']}"
            delete_response = requests.delete(delete_url, headers=headers)

            if delete_response.status_code == 204:
                total_deleted += 1
                print(f"🗑️ Deleted: '{email['subject']}' from {category} received on {email['receivedDateTime']}")
            else:
                print(f"Failed to delete: {delete_response.text}")

    print(f"\n{total_deleted} old emails deleted")

def classify_email(client, email):
    # Extract the relevant fields from the email
    sender = email['from']['emailAddress']['address']
    subject = email['subject']
    preview = email['bodyPreview'][:300]

    # Build the prompt
    prompt = f"""You are an email classifier. Classify the following email into exactly one of these categories:

- ACCOUNT_ACTIVITY: account login notifications, security alerts, 2FA codes, confirmations, account activity
- NEWSLETTER: subscribed content, gym updates, blogs, recurring promotional emails
- ACTION_REQUIRED: emails that require a reply or action from the user
- IMPORTANT: rare high-priority emails (bank, doctor, family, work)
- SPAM: useless notifications (LinkedIn, social media, marketing)
- OTHER: low importance receipts and anything that doesn't fit the above

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

def get_or_create_folder(token, folder_name):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Fetch all folders, handling pagination
    url = "https://graph.microsoft.com/v1.0/me/mailFolders"
    while url:
        response = requests.get(url, headers=headers)
        data = response.json()
        folders = data.get("value", [])

        for folder in folders:
            if folder["displayName"] == folder_name:
                #print(f"Folder '{folder_name}' already exists")
                return folder["id"]

        # Check if there's another page of folders
        url = data.get("@odata.nextLink")

    # Folder not found in any page — create it
    url = "https://graph.microsoft.com/v1.0/me/mailFolders"
    response = requests.post(url, headers=headers, json={"displayName": folder_name})

    if response.status_code == 201:
        print(f"Folder '{folder_name}' created")
        return response.json()["id"]
    else:
        raise Exception(f"Failed to create folder: {response.text}")
    
def move_email(token, email_id, folder_id):
    url = f"https://graph.microsoft.com/v1.0/me/messages/{email_id}/move"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    response = requests.post(url, headers=headers, json={"destinationId": folder_id})
    
    if response.status_code == 201:
        return True
    else:
        raise Exception(f"Failed to move email: {response.text}")

# Initialize the Anthropic client
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Get token and fetch emails
token = get_access_token()
emails = get_emails(token)

# Create folders for each category
categories = ["ACCOUNT_ACTIVITY", "NEWSLETTER", "ACTION_REQUIRED", "IMPORTANT", "SPAM", "OTHER"]
folder_ids = {}
for category in categories:
    folder_ids[category] = get_or_create_folder(token, category)
print("All folders ready!\n")

# Move emails to corresponding folder
for email in emails:
    category = classify_email(client, email)
    folder_id = folder_ids.get(category, folder_ids["OTHER"])
    move_email(token, email["id"], folder_id)
    print(f"✓ '{email['subject']}' → {category}")

# Clean up old emails in low-priority folders
categories_to_clean = ["SPAM", "NEWSLETTER", "ACCOUNT_ACTIVITY","OTHER"]
delete_old_emails(token, folder_ids, categories_to_clean, weeks_old=8)

print("Done!\n")