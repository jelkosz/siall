from googleapiclient.discovery import build
from common.formatting import formatted_label_from_config
from common.constants import LABEL, TAB, QUERY
from common.googleapi import authenticate_google

def get_config_key():
    return 'gmail-filter'

def get_config_params():
    return [LABEL, TAB, QUERY]

# takes a list of gmail queries, queries gmail and returns a map of aggregated results
# output: {'tab to which to add the results': ['label', num of messages satisgying the filter, 'link to the gmail satisfying the filter']}
def execute(config):
    creds = authenticate_google()

    label = formatted_label_from_config(config)
    query = config[QUERY]
    gmailService = build('gmail', 'v1', credentials=creds, cache_discovery=False)
        
    results = gmailService.users().messages().list(userId='me', q=query, maxResults=100, includeSpamTrash=False).execute()
    msgs = results.get('messages', [])

    if msgs:
        uniqueThreads = len(set([msg['threadId'] for msg in msgs]))
        return [label, f'=HYPERLINK(\"https://mail.google.com/mail/u/1/#search/{query}\", \"{uniqueThreads}\")']
    else:
        return []