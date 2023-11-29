import base64
import os
import logging
from typing import Dict, List, Optional, Union, Tuple
from googleapiclient.discovery import build, Resource
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from openai import OpenAI
from google.oauth2.credentials import Credentials

# Configurable variables
USER_FIRST_NAME = 'John'
USER_LAST_NAME = 'Smith'

# Setup logging
logging.basicConfig(level=logging.INFO)

# Constants
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
MAX_EMAIL_LEN = 3000  # Max length of email body to process

def get_gmail_service() -> Resource:
    """
    Authenticate and return a Gmail service resource.
    """
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

def get_openai_client() -> OpenAI:
    """
    Authenticate and return an OpenAI client.
    """
    return OpenAI()

def fetch_emails(gmail: Resource, page_token: Optional[str]) -> Tuple[List[Dict[str, Union[str, List[str]]]], Optional[str]]:
    """
    Fetch emails from Gmail and return a list of messages and the next page token.
    """
    try:
        results = gmail.users().messages().list(userId='me', labelIds=['INBOX'], pageToken=page_token).execute()
    except Exception as e:
        logging.error(f"Failed to fetch emails: {e}")
        return [], None
    messages = results.get('messages', [])
    next_page_token = results.get('nextPageToken')
    return messages, next_page_token

def parse_email_data(gmail: Resource, message_info: Dict[str, Union[str, List[str]]]) -> Dict[str, Union[str, List[str]]]:
    """
    Fetch and parse email data from Gmail.
    """
    try:
        msg = gmail.users().messages().get(userId='me', id=message_info['id'], format='full').execute()
    except Exception as e:
        logging.error(f"Failed to fetch email data: {e}")
        return {}

    try:
        headers = msg['payload']['headers']
        subject = next(header['value'] for header in headers if header['name'] == 'Subject')
        to = next(header['value'] for header in headers if header['name'] == 'To')
        sender = next(header['value'] for header in headers if header['name'] == 'From')
        cc = next((header['value'] for header in headers if header['name'] == 'Cc'), None)
    except Exception as e:
        logging.error(f"Failed to parse email data: {e}")
        return {}
    logging.info('--------------')
    logging.info(f"Email Subject: {subject}, Sender: {sender}")

    parts = msg['payload'].get('parts', [])
    body = ''
    for part in parts:
        if part['mimeType'] == 'text/plain':
            body = base64.urlsafe_b64decode(part['body'].get('data', '').encode('ASCII')).decode('utf-8')
            break

    return {
        'subject': subject,
        'to': to,
        'from': sender,
        'cc': cc,
        'labels': msg['labelIds'],
        'body': body,
    }

def evaluate_email(email_data: Dict[str, Union[str, List[str]]], user_first_name: str, user_last_name: str, client: OpenAI) -> bool:
    """
    Evaluate an email to determine if it's promotional or personal.
    """
    system_message = {
        "role": "system",
        "content": (
            "Evaluate if the email should be archived as promotional or kept in the main inbox. "
            "Promotional emails typically contain offers, discounts, marketing content, advertisements, product launches, event invitations, newsletters, are automated, or are sent in bulk. They may also include calls to action like 'Buy now', 'Sign up', or 'Join us'."
            "Personal emails directly address the user with a specific greeting, may mention them by name, or contain personalized context such as a shared event, personal relationship, or individualized information relevant to the user."
            "Transactional emails, which provide updates or information about services you use (like package notifications or account updates), should be classified as personal due to their direct relevance and practical nature."
            "Consider keywords and phrases that are commonly used in promotional content, such as 'exclusive offer', 'special discount', 'limited time', 'free trial', or 'new product'."
            "Analyze the language and tone; promotional emails often have an impersonal, sales-driven tone and may lack personalization, using generic greetings like 'Dear Customer' or 'Valued Subscriber'."
            "Acknowledge the limitations of AI in understanding nuanced human communications, and classify the email as personal, if the categorization is uncertain."
            "In cases of ambiguity, give priority to classifying the email as personal to avoid missing important communications.\n\n"
            f"User: {user_first_name} {user_last_name}\n"
            "Respond with only 'True' for promotional, 'False' for personal."
        )
    }
    truncated_body = email_data['body'][:MAX_EMAIL_LEN] + ("..." if len(email_data['body']) > MAX_EMAIL_LEN else "")
    user_message = {
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

    try:
        completion = client.chat.completions.create(model="gpt-4", messages=[system_message, user_message], max_tokens=1, temperature=0.0)
    except Exception as e:
        logging.error(f"Failed to evaluate email with GPT-4: {e}")
        return False

    return completion.choices[0].message.content.strip() == "True"

def process_email(gmail: Resource, message_info: Dict[str, Union[str, List[str]]], email_data_parsed: Dict[str, Union[str, List[str]]], user_first_name: str, user_last_name: str, client: OpenAI) -> int:
    """
    Process an individual email.
    """
    if evaluate_email(email_data_parsed, user_first_name, user_last_name, client):
        try:
            gmail.users().messages().modify(userId='me', id=message_info['id'], body={'removeLabelIds': ['UNREAD', 'INBOX']}).execute()
            logging.info("Email is not worth the time, archiving and marking as read")
            return 1
        except Exception as e:
            logging.error(f"Failed to archive and mark email as read: {e}")
    else:
        logging.info("Email is worth the time, leaving as unread")
    return 0

def report_statistics(total_unread_emails: int, total_pages_fetched: int, total_marked_as_read: int) -> None:
    """
    Report statistics of the email processing.
    """
    logging.info(f"Total number of unread emails fetched: {total_unread_emails}")
    logging.info(f"Total number of pages fetched: {total_pages_fetched}")
    logging.info(f"Total number of emails marked as read: {total_marked_as_read}")
    logging.info(f"Final number of unread emails: {total_unread_emails - total_marked_as_read}")

def main():
    """
    Main function to start the email processing.
    """
    gmail = get_gmail_service()
    client = get_openai_client()
    user_first_name = 'Seth'
    user_last_name = 'Rose'

    page_token = None
    total_unread_emails = 0
    total_pages_fetched = 0
    total_marked_as_read = 0

    while True:
        messages, page_token = fetch_emails(gmail, page_token)
        total_pages_fetched += 1

        total_unread_emails += len(messages)
        for message_info in messages:
                email_data_parsed = parse_email_data(gmail, message_info)
                # Pass the USER_FIRST_NAME and USER_LAST_NAME variables to the process_email function
                total_marked_as_read += process_email(gmail, message_info, email_data_parsed, USER_FIRST_NAME, USER_LAST_NAME, client)
        if not page_token:
            break

    report_statistics(total_unread_emails, total_pages_fetched, total_marked_as_read)

if __name__ == "__main__":
    main()
