import base64
from typing import Dict, List, Optional, Union, Tuple
from googleapiclient.discovery import build, Resource
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from openai import OpenAI
import os
from google.oauth2.credentials import Credentials

# If modifying these SCOPES, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def get_gmail_service():
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)

def get_openai_client():
    # Make sure that OPENAI_API_KEY is set in your environment
    return OpenAI()

def get_user_name():
    user_first_name = input("Enter your first name: ")
    user_last_name = input("Enter your last name: ")
    return user_first_name, user_last_name

def fetch_emails(gmail: Resource, page_token: Optional[str]) -> Tuple[List[Dict[str, Union[str, List[str]]]], Optional[str]]:
    try:
        results = gmail.users().messages().list(
            userId='me',
            labelIds=['UNREAD'],
            pageToken=page_token  # Include the page token in the request if there is one
        ).execute()
    except Exception as e:
        print(f"Failed to fetch emails: {e}")
        return [], None

    messages: List[Dict[str, Union[str, List[str]]]] = results.get('messages', [])
    page_token = results.get('nextPageToken')
    return messages, page_token

def parse_email_data(gmail: Resource, message_info: Dict[str, Union[str, List[str]]]) -> Dict[str, Union[str, List[str]]]:
    # Fetch email data with 'full' format
    try:
        msg = gmail.users().messages().get(
            userId='me', 
            id=message_info['id'],
            format='full'
        ).execute()
    except Exception as e:
        print(f"Failed to fetch email data: {e}")
        return {}

    try:
        headers = msg['payload']['headers']
        subject = next(header['value'] for header in headers if header['name'] == 'Subject')
        to = next(header['value'] for header in headers if header['name'] == 'To')
        sender = next(header['value'] for header in headers if header['name'] == 'From')
        cc = next((header['value'] for header in headers if header['name'] == 'Cc'), None)
    except Exception as e:
        print(f"Failed to parse email data: {e}")
        return {}

    print(f"Fetched email - Subject: {subject}, Sender: {sender}")

    # Extract the plain text body
    parts = msg['payload'].get('parts', [])
    for part in parts:
        if part['mimeType'] == 'text/plain':
            body = part['body'].get('data', '')
            body = base64.urlsafe_b64decode(body.encode('ASCII')).decode('utf-8')
            break
    else:
        body = ''

    # Parse email data
    email_data_parsed: Dict[str, Union[str, List[str]]] = {
        'subject': subject,
        'to': to,
        'from': sender,
        'cc': cc,
        'labels': msg['labelIds'],
        'body': body,
    }
    return email_data_parsed

def evaluate_email(email_data: Dict[str, Union[str, List[str]]], user_first_name: str, user_last_name: str, client: OpenAI) -> bool:
    MAX_EMAIL_LEN = 3000
    user_first_name = user_first_name.strip()
    user_last_name = user_last_name.strip()
    system_message: Dict[str, str] = {
        "role": "system",
        "content": (
            "Your task is to assist in managing the Gmail inbox of a busy individual, "
            f"{user_first_name} {user_last_name}, by filtering out promotional emails "
            "from her personal (i.e., not work) account. Your primary focus is to ensure "
            "that emails from individual people, whether they are known family members (with the "
            f"same last name), close acquaintances, or potential contacts {user_first_name} might be interested "
            "in hearing from, are not ignored. You need to distinguish between promotional, automated, "
            "or mass-sent emails and personal communications.\n\n"
            "Respond with \"True\" if the email is promotional and should be ignored based on "
            "the below criteria, or \"False\" otherwise. Remember to prioritize personal "
            "communications and ensure emails from genuine individuals are not filtered out.\n\n"
            "Criteria for Ignoring an Email:\n"
            "- The email is promotional: It contains offers, discounts, or is marketing a product "
            "or service.\n"
            "- The email is automated: It is sent by a system or service automatically, and not a "
            "real person.\n"
            "- The email appears to be mass-sent or from a non-essential mailing list: It does not "
            f"address {user_first_name} by name, lacks personal context that would indicate it's personally written "
            "to her, or is from a mailing list that does not pertain to her interests or work.\n\n"
            "Special Consideration:\n"
            "- Exception: If the email is from an actual person, especially a family member (with the "
            f"same last name), a close acquaintance, or a potential contact {user_first_name} might be interested in, "
            "and contains personalized information indicating a one-to-one communication, do not mark "
            "it for ignoring regardless of the promotional content.\n\n"
            "- Additionally, do not ignore emails requiring an action to be taken for important matters, "
            "such as needing to send a payment via Venmo, but ignore requests for non-essential actions "
            "like purchasing discounted items or signing up for rewards programs.\n\n"
            "Be cautious: If there's any doubt about whether an email is promotional or personal, "
            "respond with \"False\".\n\n"
            "The user message you will receive will have the following format:\n"
            "Subject: <email subject>\n"
            "To: <to names, to emails>\n"
            "From: <from name, from email>\n"
            "Cc: <cc names, cc emails>\n"
            "Gmail labels: <labels>\n"
            "Body: <plaintext body of the email>\n\n"
            "Your response must be:\n"
            "\"True\" or \"False\""
        )
    }
    truncated_body = (email_data['body'][:MAX_EMAIL_LEN] + ("..." if len(email_data['body']) > MAX_EMAIL_LEN else "")) if 'body' in email_data else ""

    user_message: Dict[str, str] = {
        "role": "user",
        "content": (
            f"Subject: {email_data['subject']}\n"
            f"To: {email_data['to']}\n"
            f"From: {email_data['from']}\n"
            f"Cc: {email_data['cc']}\n"
            f"Gmail labels: {email_data['labels']}\n"
            f"Body: {truncated_body}"
        )
    }

    # Send the messages to GPT-4, TODO add retry logic
    try:
        completion = client.chat.completions.create(
            model="gpt-4", # switch to gpt-3.5-turbo for faster/ cheaper results (might be slightly less accurate)
            messages=[system_message, user_message],
            max_tokens=1,
            temperature=0.0,
        )
    except Exception as e:
        print(f"Failed to evaluate email with GPT-4: {e}")
        return False

    # Extract and return the response
    return completion.choices[0].message.content.strip() == "True"

def process_email(gmail: Resource, message_info: Dict[str, Union[str, List[str]]], email_data_parsed: Dict[str, Union[str, List[str]]], user_first_name: str, user_last_name: str, client: OpenAI) -> int:
    try:
        should_mark_as_read = evaluate_email(email_data_parsed, user_first_name, user_last_name, client)
    except Exception as e:
        print(f"Failed to evaluate email: {e}")
        return 0
    
    # Evaluate email
    if should_mark_as_read:
        print("Email is not worth the time, marking as read")
        # Remove UNREAD label
        try:
            gmail.users().messages().modify(
                userId='me',
                id=message_info['id'],
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            print("Email marked as read successfully")
            return 1
        except Exception as e:
            print(f"Failed to mark email as read: {e}")
    else:
        print("Email is worth the time, leaving as unread")
    return 0

def report_statistics(total_unread_emails: int, total_pages_fetched: int, total_marked_as_read: int) -> None:
    print(f"Total number of unread emails fetched: {total_unread_emails}")
    print(f"Total number of pages fetched: {total_pages_fetched}")
    print(f"Total number of emails marked as read: {total_marked_as_read}")
    print(f"Final number of unread emails: {total_unread_emails - total_marked_as_read}")

def main():
    gmail = get_gmail_service()
    client = get_openai_client()
    user_first_name, user_last_name = get_user_name()

    page_token: Optional[str] = None

    total_unread_emails = 0
    total_pages_fetched = 0
    total_marked_as_read = 0

    while True:  # Continue looping until no more pages of messages
        # Fetch unread emails
        messages, page_token = fetch_emails(gmail, page_token)
        total_pages_fetched += 1
        print(f"Fetched page {total_pages_fetched} of emails")

        total_unread_emails += len(messages)
        for message_info in messages: # TODO process emails on a single page in parallel
            # Fetch and parse email data
            email_data_parsed = parse_email_data(gmail, message_info)

            # Process email
            total_marked_as_read += process_email(gmail, message_info, email_data_parsed, user_first_name, user_last_name, client)

        if not page_token:
            break  # Exit the loop if there are no more pages of messages

    report_statistics(total_unread_emails, total_pages_fetched, total_marked_as_read)

if __name__ == "__main__":
    main()