from __future__ import print_function

import json
import os
from datetime import datetime
import time
import logging
import sys

from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from common.constants import *
from common.googleapi import authenticate_google

def sheet(creds):
    spreadsheetService = build('sheets', 'v4', credentials=creds, cache_discovery=False)
    return spreadsheetService.spreadsheets()

def parse_row(row, params, formattedRow = None, rowid = -1):
    res = {}
    for colid, col in enumerate(row):
        for param in params:
            if col.startswith(param):
                res[param] = col[len(param):len(col)].strip()
                if formattedRow is not None:
                    res[param + '-format'] = formattedRow[rowid][colid]
    res[RAW_ROW] = row

    return res

def load_sheet_metadata(creds):
    sheets = sheet(creds).get(spreadsheetId=SPREADSHEET_ID).execute().get('sheets', [])
    res = {}
    for oneSheet in sheets:
        res[oneSheet['properties']['title']] = oneSheet['properties']['sheetId']

    return res

def load_confg(creds, modules):    
    formattedRows = normalize_data_and_format(get_sheet_formats(creds, "config").get('sheets', [])[0].get('data', [])[0].get('rowData', []))
    data = formattedRows[0]
    formats = formattedRows[1]
    
    res = {}
    for module_key in modules:
        res[module_key] = []

    if data:
        for rowid, row in enumerate(data):
            if row[0] in res:
                res[row[0]].append(parse_row(row, modules[row[0]].get_config_params(), formats, rowid))
    return res

def clear_spreadsheet(creds, targetRange, sheetId, numOfLinesToClear):
    deleteRows = {
        "requests": [
            {
            "deleteDimension": {
                "range": {
                "sheetId": sheetId,
                "dimension": "ROWS",
                "startIndex": 0,
                "endIndex": numOfLinesToClear - 1
                }
            }
            }
        ]
    }
    sheet(creds).batchUpdate(spreadsheetId=SPREADSHEET_ID, body=deleteRows).execute()

def boldFormat(bold):
    return [{'userEnteredFormat': {'textFormat': {'bold': bold}}}]

def add_formatted(newValues, row, sheetId, formatBody, formats):
    newValues.append(row)

    for col, format in enumerate(formats):
        formatBody['requests'].append({
                'repeatCell': {
                    'range': {'startRowIndex': len(newValues) - 1,
                            'endRowIndex': len(newValues),
                            'startColumnIndex': col,
                            'endColumnIndex': col + 1,
                            'sheetId': sheetId
                        },
                    'cell': format,
                    'fields': 'userEnteredFormat',
                }
            })

# The newVlaues is a list of eiter strings (e.g. value to print to the doc) or a dict
# which looks like {'value': 'some value to print', 'format': 'the format in which it shold be printed'}
def add_formatted_from_values(newValues, row, sheetId, formatBody):
    rowValues = []
    rowFormats = []
    for col in row:
        if hasattr(col, 'get'):
            rowValues.append(col.get('value', ''))
            rowFormats.append(col.get('format', {'userEnteredFormat': {'textFormat': {'bold': False}}}))
        else:
            rowValues.append(col)
            rowFormats.append({'userEnteredFormat': {'textFormat': {'bold': False}}})
    
    add_formatted(newValues, rowValues, sheetId, formatBody, rowFormats)

# Splits the combination of data and format to two separate parts making sure that there is format for each data entry and vice versa
def normalize_data_and_format(formattedRows):
    resData = []
    resFormats = []
    for row in formattedRows:
        dataRow = []
        formatRow = []
        resData.append(dataRow)
        resFormats.append(formatRow)
        for col in row.get('values', []):
            dataVal = col.get('userEnteredValue', {}).get('stringValue', '')
            dataRow.append(dataVal)
            formatRow.append({'userEnteredFormat': col.get('userEnteredFormat', {'textFormat': {'bold': False}})})

    return (resData, resFormats)


def add_column_heights(numOfRows, sheetId, formatBody):
    body = {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheetId,
                    "dimension": "ROWS",
                    "startIndex": 0,
                    "endIndex": numOfRows
                },
                "properties": {
                    "pixelSize": 20
                },
                "fields": "pixelSize"
            }
            }
    formatBody['requests'].append(body)

# toUpdate format:
# {'the section name': [new values]}
# The behavior:
# If the section is in the toUpdate and it has some values (eg non empty list), the section content will be replaced by the values
# If the section is in the toUpdate and it has an empty list as a value, the whole section will be removed from the result
# If the section is not in the toUpdate, it will be ignored (e.g. the content of the section will be preserved as is)
def refresh_spreadsheet(creds, toUpdate, targetRange, sheetMetadata):
    formattedRows = normalize_data_and_format(get_sheet_formats(creds, targetRange).get('sheets', [])[0].get('data', [])[0].get('rowData', []))
    data = formattedRows[0]
    formats = formattedRows[1]

    # the output which will be sent to the spreadsheet api
    newValues = []
    
    # list of "sections" which have been updated - used to know the "toUpdate" contains something which is not yet present in the spreadsheet
    updatedSections = []
    copyRow = False
    sheetId = sheetMetadata[targetRange]

    formatBody = {
        'requests': []
    }

    for sourceDataIndex, row in enumerate(data):
        if len(row) > 0 and row[0].startswith(SECTION):
            section = parse_row(row, [SECTION])[SECTION]
            if section in toUpdate and len(toUpdate[section]) != 0:
                add_formatted(newValues, row, sheetId, formatBody, boldFormat(True))
                updatedSections.append(section)

                for newValue in toUpdate[section]:
                    add_formatted_from_values(newValues, newValue, sheetId, formatBody)
                # content replaced by new values (e.g. updated), ignore the original values until next section
                copyRow = False
            if section in toUpdate and len(toUpdate[section]) == 0:
                # it needs to be completely removed, ignore all other rows
                copyRow = False
            if section not in toUpdate:
                add_formatted(newValues, row, sheetId, formatBody, boldFormat(True))
                # no mention in the toUpdate, just copy the conent over
                copyRow = True
        else:
            if copyRow:
                # copy
                add_formatted(newValues, row, sheetId, formatBody, formats[sourceDataIndex])

    for newSection in toUpdate:
        # this is a new section, needs to be added to the output
        if newSection not in updatedSections and len(toUpdate[newSection]) != 0:
            add_formatted(newValues, [SECTION + ' ' + newSection], sheetId, formatBody, boldFormat(True))
            for newValue in toUpdate[newSection]:
                add_formatted_from_values(newValues, newValue, sheetId, formatBody)


    add_column_heights(len(newValues), sheetId, formatBody)
    write_to_spreadsheet(creds, newValues, targetRange, sheetId, formatBody, len(data))

def write_to_spreadsheet(creds, values, targetRange, sheetId, formatBody, numOfLinesToClear):
    clear_spreadsheet(creds, targetRange, sheetId, numOfLinesToClear)

    body = {
        'values': values
    }
    sheet(creds).values().update(
        spreadsheetId=SPREADSHEET_ID, range=targetRange,
        valueInputOption='USER_ENTERED', body=body).execute()

    if formatBody is not None:
        sheet(creds).batchUpdate(spreadsheetId=SPREADSHEET_ID, body=formatBody).execute()

def extract_from_config(config, key, allowDuplicates=True):
    res = []
    for instance in config:
        for category in config[instance]:
            val = category[key]
            if allowDuplicates or val not in res:
                res.append(val)

    return res

def get_sheet_formats(creds, targetRange):
    params = {'spreadsheetId': SPREADSHEET_ID,
              'ranges': targetRange,
              'fields': 'sheets(data(rowData(values(userEnteredFormat,userEnteredValue)),startColumn,startRow))'}
    return sheet(creds).get(**params).execute()

def main():
    logging.basicConfig(
        stream=sys.stdout,
        format='%(asctime)s %(levelname)-8s %(message)s',
        level=logging.INFO,
        datefmt='%Y-%m-%d %H:%M:%S')

    logging.info('Loading plugins')


    sys.path.append('plugins')
    plugins = {}
    for file in os.listdir("plugins"):
        if file.endswith(".py"):
            name = file.removesuffix('.py')
            if name == '__init__':
                continue

            logging.info(f'Trying to load plguin {name}')
            module = __import__(name)
            plugins[module.get_config_key()] = module
            logging.info(f'Plguin {name} loaded')

    timeout = 10 * 60
    while True:
        logging.info('Loading common config')
        googleCreds = authenticate_google()
        sheetMetadata = load_sheet_metadata(googleCreds)
        config = load_confg(googleCreds, plugins)
        tabs = extract_from_config(config, TAB, False)
        logging.info('Configs loaded')

        logging.info('Executing plugins')
        results = {}
        for plugin_name in plugins:
            logging.info(f'Executing plugin {plugin_name}')
            res = plugins[plugin_name].execute(config[plugin_name])
            results[plugin_name] = res
            logging.info(f'Executed plugin {plugin_name}')
        
        logging.info('All plugins executed, updating output spreadsheet')
        for tab in tabs:
            toUpdate = {}
            for plugin_name in results:
                if tab in results[plugin_name]:
                    toUpdate[plugin_name] = results[plugin_name][tab]
            logging.info(f'Updating tab {tab}')
            refresh_spreadsheet(googleCreds, toUpdate, tab, sheetMetadata)       

        logging.info(f'All tabs updated, sleeping for {timeout}s')
        time.sleep(timeout)

if __name__ == '__main__':
    main()

# TODO:
# sorting of the bz output
# sorting of the sections
# lock the sheet while updating it
# jira integration
# send a notification under some conditions
# if there is exactly one BZ which satisfies the filter, the result is just "1" without the split + all etc
# add option to have WIP limits
# optimize: the sheet() does not need to be called repeatedly
# sometimes it fails on: Details: "Invalid requests[0].deleteDimension: You can't delete all the rows on the sheet."
# format the section titles to be prettier
# add support for conditional formatting (e.g. if the num of bugs is higher than X than make it red)