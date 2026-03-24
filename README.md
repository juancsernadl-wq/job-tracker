# Job Tracker

An AI-powered tool that automatically scans your Gmail inbox for job application emails, extracts key information using Claude AI, and logs everything into a structured Google Sheet — with automatic status updates when follow-up emails arrive.

## What it does

- Scans Gmail for job application confirmation and follow-up emails
- Uses Claude AI to extract company name, role, date, and application status
- Saves results to a Google Sheet with duplicate detection
- Automatically updates the status when a follow-up email is found (e.g. Applied → Interview → Rejected)
- Filters out promotional and non-job-related emails using AI judgment
- Runs automatically every 2 days via a scheduled cron job

## Tech stack

- Python
- Gmail API (Google Cloud)
- Google Sheets API
- Anthropic Claude API (claude-haiku)
- gspread, MSAL, python-dotenv

## How it works

1. Authenticates with Gmail using OAuth2
2. Searches for emails matching job application keywords
3. Sends each email body to Claude with a structured prompt
4. Claude returns a JSON object with company, role, date, status, and notes
5. The script checks for duplicates and status changes before writing to the sheet
6. A cron job runs the script every 2 days at 4pm automatically

## Setup

1. Clone the repo
2. Create a virtual environment and install dependencies:
```
   pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client anthropic gspread python-dotenv
```
3. Set up a Google Cloud project and enable Gmail API and Sheets API
4. Download your OAuth credentials as `credentials.json`
5. Create a `.env` file with your API keys:
```
   ANTHROPIC_API_KEY=your-key-here
```
6. Add your Google Sheet ID to the `SPREADSHEET_ID` variable in `gmail_reader.py`
7. Run the script:
```
   python gmail_reader.py
```

## Example output

| Company | Role | Date | Status | Notes |
|---|---|---|---|---|
| Acme Corp | Product Manager | 2026-03-01 | Applied | Application confirmation received |
| Google | Unknown | Unknown | Interview | Candidate invited to complete hiring assessment |
| Western Digital | Business Analyst | Unknown | Rejected | Application rejected; skills did not align |

## Notes

- Sensitive files (`.env`, `credentials.json`, `token.pickle`) are excluded via `.gitignore`
- The script uses Claude Haiku for cost efficiency — each full run costs a few cents
- Built as a personal productivity tool during an active MBA job search
