from __future__ import print_function

import requests
import json
import pickle
import os.path
from datetime import datetime
import time
import logging
import sys

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SPREADSHEET_ID = '1JAZXnfmyx8yQ3yeBcKORfMn9sGot-VzWPHUVPJRhPNg'

GMAIL_FILTER_CONFIG = 'gmail-filter'
BZ_FILTER_CONFIG = 'bz-filter'

# PUBLIC PARAMETERS

# generic parameters

# label: the label printed next to it
LABEL = 'label:'
# tab: the tab to which it will be printed
TAB = 'tab:'
# query: filter query it has to satisfy
QUERY = 'query:'

LAST_SUCCESSFUL_EXECUTION_TIMESTAMP = 'lastSuccessfulExecution:'
LAST_EXECUTION_STATUS = 'lastExecutionStatus:'
STATUS_SUCCESS = 'Success'
STATUS_ERROR = 'ERROR'

# bugzilla specific parameters
# how the result should be split (e.g. by status/priority/severity)
SPLIT_BY = 'splitBy:'

# INTERNAL CONSTANTS
# Section of output
SECTION = 'section:'
RAW_ROW = 'rawRow'

def authenticate_google():
    # If modifying these scopes, delete the file token.pickle.
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/gmail.readonly']
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return creds

def load_bz_api_key():
    msg = 'Problem loading bugzilla API key. Please login to bugzilla web interface, go to Preferences->API Keys, generate a new one and paste it into a file named bz.apikey next to this file.'
    if os.path.exists('bz.apikey'):
        with open('bz.apikey', 'r') as apiKey:
            key = apiKey.readline().strip()
            if key is None:
                logging.error(msg)
            return key
    else:
        logging.error(msg)

def sheet(creds):
    spreadsheetService = build('sheets', 'v4', credentials=creds, cache_discovery=False)
    return spreadsheetService.spreadsheets()

def parse_row(row, params):
    res = {}
    for col in row:
        for param in params:
            if col.startswith(param):    
                res[param] = col[len(param):len(col)].strip()
    res[RAW_ROW] = row
    return res

def set_execution_status(config, status):
    row = config[RAW_ROW]
    parsed = parse_row(row, [LAST_EXECUTION_STATUS, LAST_SUCCESSFUL_EXECUTION_TIMESTAMP])

    def add_or_replace(arr, key, value):
        if value is None:
            return arr

        if key in parsed:
            return [f'{key}{value}' if col.startswith(key) else col for col in arr]
        else:
            return arr + [f'{key}{value}']
    
    
    timestamp = None
    if status == STATUS_SUCCESS:
        timestamp = datetime.now().strftime("%H:%M:%S")
    lastStatus = add_or_replace(row, LAST_EXECUTION_STATUS, status)
    config[RAW_ROW] = add_or_replace(lastStatus, LAST_SUCCESSFUL_EXECUTION_TIMESTAMP, timestamp)

def load_sheet_metadata(creds):
    sheets = sheet(creds).get(spreadsheetId=SPREADSHEET_ID).execute().get('sheets', [])
    res = {}
    for oneSheet in sheets:
        res[oneSheet['properties']['title']] = oneSheet['properties']['sheetId']

    return res

def extract_from_config(config, key, allowDuplicates=True):
    res = []
    for instance in config:
        for category in config[instance]:
            val = category[key]
            if allowDuplicates or val not in res:
                res.append(val)

    return res

def load_confg(creds):    
    result = sheet(creds).values().get(spreadsheetId=SPREADSHEET_ID,
                                range='Config!A1:H').execute()
    values = result.get('values', [])

    gmailFilterConfigs = []
    bzFilterConfigs = []
    res = {}
    res[GMAIL_FILTER_CONFIG] = gmailFilterConfigs
    res[BZ_FILTER_CONFIG] = bzFilterConfigs

    if values:
        for row in values:
            if row[0] == GMAIL_FILTER_CONFIG:
                gmailFilterConfigs.append(parse_row(row, [LABEL, TAB, QUERY, LAST_SUCCESSFUL_EXECUTION_TIMESTAMP, LAST_EXECUTION_STATUS]))
            if row[0] == BZ_FILTER_CONFIG:
                bzFilterConfigs.append(parse_row(row, [LABEL, TAB, QUERY, SPLIT_BY, LAST_SUCCESSFUL_EXECUTION_TIMESTAMP, LAST_EXECUTION_STATUS]))

    return res

def clear_spreadsheet(creds, targetRange):
  sheet(creds).values().clear(spreadsheetId=SPREADSHEET_ID, range=targetRange).execute()   


def add_formatted(newValues, row, sheetId, formatBody, bold):
    newValues.append(row)
    formatBody['requests'].append({
                'repeatCell': {
                    'range': {'startRowIndex': len(newValues) - 1, 'endRowIndex': len(newValues), 'sheetId': sheetId},
                    'cell': {'userEnteredFormat': {'textFormat': {'bold': bold}}},
                    'fields': 'userEnteredFormat.textFormat.bold',
                }
            })

# toUpdate format:
# {'the section name': [new values]}
# The behavior:
# If the section is in the toUpdate and it has some values (eg non empty list), the section content will be replaced by the values
# If the section is in the toUpdate and it has an empty list as a value, the whole section will be removed from the result
# If the section is not in the toUpdate, it will be ignored (e.g. the content of the section will be preserved as is)
def refresh_spreadsheet(creds, toUpdate, targetRange, sheetMetadata):
    result = sheet(creds).values().get(spreadsheetId=SPREADSHEET_ID,
                                range=targetRange).execute()
    values = result.get('values', [])
    # the output which will be sent to the spreadsheet api
    newValues = []
    
    # list of "sections" which have been updated - used to know the "toUpdate" contains something which is not yet present in the spreadsheet
    updatedSections = []
    copyRow = False
    
    formatBody = {
        'requests': []
    }

    for row in values:
        if len(row) > 0 and row[0].startswith(SECTION):
            section = parse_row(row, [SECTION])[SECTION]
            if section in toUpdate and len(toUpdate[section]) != 0:
                add_formatted(newValues, row, sheetMetadata[targetRange], formatBody, True)
                updatedSections.append(section)

                for newValue in toUpdate[section]:
                    add_formatted(newValues, newValue, sheetMetadata[targetRange], formatBody, False)
                # content replaced by new values (e.g. updated), ignore the original values until next section
                copyRow = False
            if section in toUpdate and len(toUpdate[section]) == 0:
                # it needs to be completely removed, ignore all other rows
                copyRow = False
            if section not in toUpdate:
                add_formatted(newValues, row, sheetMetadata[targetRange], formatBody, True)
                # no mention in the toUpdate, just copy the conent over
                copyRow = True
        else:
            if copyRow:
                # copy
                add_formatted(newValues, row, sheetMetadata[targetRange], formatBody, False)
    
    for newSection in toUpdate:
        # this is a new section, needs to be added to the output
        if newSection not in updatedSections and len(toUpdate[newSection]) != 0:
            add_formatted(newValues, [SECTION + ' ' + newSection], sheetMetadata[targetRange], formatBody, True)
            for newValue in toUpdate[newSection]:
                add_formatted(newValues, newValue, sheetMetadata[targetRange], formatBody, False)

    write_to_spreadsheet(creds, newValues, targetRange, formatBody)

def write_to_spreadsheet(creds, values, targetRange, formatBody):
    clear_spreadsheet(creds, targetRange)

    body = {
        'values': values
    }
    result = sheet(creds).values().update(
        spreadsheetId=SPREADSHEET_ID, range=targetRange,
        valueInputOption='USER_ENTERED', body=body).execute()

    if formatBody is not None:
        sheet(creds).batchUpdate(spreadsheetId=SPREADSHEET_ID, body=formatBody).execute()

# takes a list of gmail queries, queries gmail and returns a map of aggregated results
# output: {'tab to which to add the results': ['label', num of messages satisgying the filter, 'link to the gmail satisfying the filter']}
def load_gmail_by_filter(creds, configs):
    res = {}
    for config in configs:
        try:
            if config[TAB] not in res:
                res[config[TAB]] = []
            query = config[QUERY]
            gmailService = build('gmail', 'v1', credentials=creds, cache_discovery=False)
        
            results = gmailService.users().messages().list(userId='me', q=query, maxResults=100, includeSpamTrash=True).execute()
            msgs = results.get('messages', [])

            if msgs:
                res[config[TAB]].append([config[LABEL], f'=HYPERLINK(\"https://mail.google.com/mail/u/1/#search/{query}\", \"{len(msgs)}\")'])
            
            set_execution_status(config, STATUS_SUCCESS)

        except:
            set_execution_status(config, STATUS_ERROR)


    return res

def load_bz_by_filter(apiKey, configs):
    res = {}
    for config in configs:
        try:
            if config[TAB] not in res:
                res[config[TAB]] = []

            headers = {'Content-Type': 'application/json', 'Accpet': 'application/json'}
            query = {
                'api_key': apiKey,
            }

            raw = requests.get(f'https://bugzilla.redhat.com/rest/bug?{config[QUERY]}', params=query, headers=headers)
            bzs = raw.json()['bugs']
            if (SPLIT_BY not in config):
                res[config[TAB]].append([config[LABEL], f'=HYPERLINK(\"https://bugzilla.redhat.com/buglist.cgi?{config[QUERY]}\", \"{len(bzs)}\")'])
            else:
                splitBy = config[SPLIT_BY]
                values = [config[LABEL], f'=HYPERLINK(\"https://bugzilla.redhat.com/buglist.cgi?{config[QUERY]}\", \"All: {len(bzs)}\")']
                res[config[TAB]].append(values)
                
                splitToCounts = {}
                for bz in bzs:
                    if bz[splitBy] in splitToCounts:
                        splitToCounts[bz[splitBy]] = splitToCounts[bz[splitBy]] + 1
                    else:
                        splitToCounts[bz[splitBy]] = 1
                for splitToCount in splitToCounts:
                    values.append(f'{splitToCount}: {splitToCounts[splitToCount]}')
       
            set_execution_status(config, STATUS_SUCCESS)
        except:
            set_execution_status(config, STATUS_ERROR)

    return res

# Update the Config tab by adding the execution status
def update_config(creds, config):
    write_to_spreadsheet(creds, extract_from_config(config, RAW_ROW), 'Config', None)

def main():
    # logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    logging.basicConfig(
        stream=sys.stdout,
        format='%(asctime)s %(levelname)-8s %(message)s',
        level=logging.INFO,
        datefmt='%Y-%m-%d %H:%M:%S')

    logging.info('Loading configs')
    googleCreds = authenticate_google()
    config = load_confg(googleCreds)
    tabs = extract_from_config(config, TAB, False)
    sheetMetadata = load_sheet_metadata(googleCreds)
    bzApiKey = load_bz_api_key()
    logging.info('Configs loaded, starting loop\n')

    timeout = 5 * 60
    while True:
        logging.info('New calmifycation cycle starting')
        try:
            logging.info('Loading gmail')
            mails = load_gmail_by_filter(googleCreds, config[GMAIL_FILTER_CONFIG])
            logging.info('Loaded')

            logging.info('Loading bugzilla')
            bzs = load_bz_by_filter(bzApiKey, config[BZ_FILTER_CONFIG])
            logging.info('Loaded')

            logging.info('Updating output spreadsheet')
            update_config(googleCreds, config)

            for tab in tabs:
                toUpdate = {}
                if tab in mails:
                    toUpdate[GMAIL_FILTER_CONFIG] = mails[tab]
                if tab in bzs:
                    toUpdate[BZ_FILTER_CONFIG] = bzs[tab]

                refresh_spreadsheet(googleCreds, toUpdate, tab, sheetMetadata)
            logging.info('Updated')
            logging.info(f'Calmifycation cycle over, sleeping for {timeout} seconds\n')
        except:
            logging.error('Calmifycation failed')

        time.sleep(timeout)

if __name__ == '__main__':
    main()
