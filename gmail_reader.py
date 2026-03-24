import os
import pickle
import base64
import json
import anthropic
from datetime import datetime
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

load_dotenv()

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/spreadsheets'
]

SPREADSHEET_ID = '1fdV_mBK6oibMdKmcxFnRQbMrb4pi4TIa939ux6O2EsE'

def get_credentials():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return creds

def get_gmail_service(creds):
    return build('gmail', 'v1', credentials=creds)

def get_sheets_service(creds):
    return build('sheets', 'v4', credentials=creds)

def get_email_body(message):
    try:
        payload = message['payload']
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body']['data']
                    return base64.urlsafe_b64decode(data).decode('utf-8')
                if 'parts' in part:
                    for subpart in part['parts']:
                        if subpart['mimeType'] == 'text/plain':
                            data = subpart['body']['data']
                            return base64.urlsafe_b64decode(data).decode('utf-8')
        elif 'body' in payload and 'data' in payload['body']:
            return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
    except Exception:
        return None
    return None

def parse_with_claude(email_body, subject, sender):
    client = anthropic.Anthropic()
    prompt = f"""You are helping track job applications. Analyze this email and extract the following info.
You MUST respond with a single JSON object and nothing else — no markdown, no code blocks, no explanation.

Fields to extract:
- is_job_related: true if this is a job application, interview, or recruiting email — false if it is promotional, marketing, rewards, LinkedIn recommendation, or unrelated
- company: the company name
- role: the job title or position
- date: the date of the email (as YYYY-MM-DD if possible, otherwise "Unknown")
- status: one of "Applied", "Interview", "Rejected", "Offer", or "Unknown"
- notes: a one-sentence summary

Email sender: {sender}
Email subject: {subject}
Email body:
{email_body[:2000]}

Respond with ONLY a JSON object like this:
{{"is_job_related": true, "company": "Acme Corp", "role": "Product Manager", "date": "2025-03-01", "status": "Applied", "notes": "Confirmation email received."}}"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text

def clean_and_parse_json(raw):
    cleaned = raw.strip()
    if cleaned.startswith('```'):
        cleaned = cleaned.split('\n', 1)[1]
    if cleaned.endswith('```'):
        cleaned = cleaned.rsplit('```', 1)[0]
    cleaned = cleaned.strip()
    data = json.loads(cleaned)
    if isinstance(data, list):
        data = data[0]
    return data

def get_existing_entries(sheets_service):
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range='Sheet1!A:F'
    ).execute()
    rows = result.get('values', [])
    entries = {}
    for i, row in enumerate(rows[1:], start=2):
        if len(row) >= 2:
            key = f"{row[0].strip().lower()}|{row[1].strip().lower()}"
            entries[key] = {
                'row_index': i,
                'company': row[0] if len(row) > 0 else '',
                'role': row[1] if len(row) > 1 else '',
                'date': row[2] if len(row) > 2 else '',
                'status': row[3] if len(row) > 3 else '',
                'notes': row[4] if len(row) > 4 else '',
                'last_updated': row[5] if len(row) > 5 else ''
            }
    return entries

def setup_sheet(sheets_service):
    headers = [['Company', 'Role', 'Date', 'Status', 'Notes', 'Last Updated']]
    sheets_service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range='Sheet1!A1:F1',
        valueInputOption='RAW',
        body={'values': headers}
    ).execute()

def update_existing_row(sheets_service, row_index, data, new_note):
    today = datetime.today().strftime('%Y-%m-%d')
    updated_values = [[
        data.get('company', ''),
        data.get('role', ''),
        data.get('date', ''),
        data.get('status', ''),
        new_note,
        today
    ]]
    sheets_service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f'Sheet1!A{row_index}:F{row_index}',
        valueInputOption='RAW',
        body={'values': updated_values}
    ).execute()
    print(f"Updated: {data.get('company')} - {data.get('role')} → {data.get('status')} (as of {today})")

def save_new_row(sheets_service, data, existing_entries):
    company = data.get('company', '').strip()
    role = data.get('role', '').strip()
    today = datetime.today().strftime('%Y-%m-%d')
    row = [[
        company,
        role,
        data.get('date', ''),
        data.get('status', ''),
        data.get('notes', ''),
        today
    ]]
    sheets_service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range='Sheet1!A:F',
        valueInputOption='RAW',
        insertDataOption='INSERT_ROWS',
        body={'values': row}
    ).execute()
    print(f"Saved: {company} - {role}")
    key = f"{company.lower()}|{role.lower()}"
    existing_entries[key] = {'row_index': None, 'status': data.get('status', '')}

def process_email(sheets_service, data, existing_entries):
    if not data.get('is_job_related', True):
        print(f"Skipped (not job related): {data.get('company', 'unknown')}")
        return

    company = data.get('company', '').strip()
    role = data.get('role', '').strip()
    new_status = data.get('status', 'Unknown')
    new_notes = data.get('notes', '')
    key = f"{company.lower()}|{role.lower()}"

    if key in existing_entries:
        existing = existing_entries[key]
        old_status = existing.get('status', 'Unknown')
        status_rank = {'Unknown': 0, 'Applied': 1, 'Interview': 2, 'Offer': 3, 'Rejected': 4}
        if status_rank.get(new_status, 0) > status_rank.get(old_status, 0):
            today = datetime.today().strftime('%Y-%m-%d')
            updated_note = f"{new_notes} [Updated {today}: {old_status} → {new_status}]"
            data['company'] = company
            data['role'] = role
            update_existing_row(sheets_service, existing['row_index'], data, updated_note)
            existing_entries[key]['status'] = new_status
        else:
            print(f"Skipped (no status change): {company} - {role} still '{old_status}'")
    else:
        save_new_row(sheets_service, data, existing_entries)

def search_and_parse_emails(gmail_service, sheets_service, existing_entries):
    query = 'subject:(application OR "thank you for applying" OR "we received your application" OR "your application" OR "interview" OR "unfortunately" OR "next steps" OR "offer")'
    result = gmail_service.users().messages().list(userId='me', q=query, maxResults=50).execute()
    messages = result.get('messages', [])
    print(f"Found {len(messages)} emails. Parsing with Claude...\n")

    for msg in messages:
        full_msg = gmail_service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
        headers = {h['name']: h['value'] for h in full_msg['payload']['headers']}
        subject = headers.get('Subject', 'No subject')
        sender = headers.get('From', 'Unknown sender')
        body = get_email_body(full_msg)

        if not body:
            print(f"Skipped (no body): {subject[:60]}")
            continue

        print(f"Parsing: {subject[:60]}...")
        try:
            parsed_raw = parse_with_claude(body, subject, sender)
            data = clean_and_parse_json(parsed_raw)
            process_email(sheets_service, data, existing_entries)
        except Exception as e:
            print(f"Error processing email: {e}")

if __name__ == '__main__':
    creds = get_credentials()
    gmail_service = get_gmail_service(creds)
    sheets_service = get_sheets_service(creds)
    setup_sheet(sheets_service)
    existing_entries = get_existing_entries(sheets_service)
    print(f"Found {len(existing_entries)} existing entries in sheet.\n")
    search_and_parse_emails(gmail_service, sheets_service, existing_entries)
    print("\nDone! Check your Google Sheet.")