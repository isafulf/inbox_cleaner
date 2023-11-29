# Inbox Cleaner

This script automates the organization of a Gmail inbox by identifying and archiving promotional emails. It uses advanced language models, such as GPT-3 or GPT-4, to determine which emails are promotional.

## Prerequisites

- Python 3.7 or higher
- A Gmail account
- A Google Cloud account with the Gmail API enabled
- An OpenAI API key

## Setup

1. Clone the repository:

   ```sh
   git clone https://github.com/isafulf/inbox_cleaner.git
   cd inbox_cleaner
   ```

2. Install the required Python packages:

   ```sh
   pip install -r requirements.txt
   ```

3. Set up Google API credentials:

   - Create a new OAuth 2.0 Client ID by following the instructions [here](https://developers.google.com/workspace/guides/create-credentials).
   - Download the JSON file and rename it to `credentials.json`.
   - Place `credentials.json` in the `inbox_cleaner` directory.

4. Set up your OpenAI API key:

   - Secure an OpenAI API key by following the instructions [here](https://platform.openai.com/api-keys).
   - Assign the key to an environment variable for use in the application:

     ```sh
     export OPENAI_API_KEY=<your_openai_api_key>
     ```

## Usage

Before running the script, be sure to have your OpenAI API key set as an environment variable as shown in the setup instructions. Once done, execute the script with:

```sh
python process_all_unread_emails.py
```

The script will commence by authenticating with the Gmail API and the OpenAI API, then proceed to fetch all unread emails in your inbox and evaluate each one to determine if it's promotional. If an email is identified as promotional based on the response from GPT-3 or GPT-4, it will be archived and marked as read. Otherwise, the email will remain in your inbox as unread.
