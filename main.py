from __future__ import print_function

import json
import os
from datetime import datetime
import time
import logging
import sys
import getopt

from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from common.constants import *
from common.googleapi import authenticate_google
from common.formatting import boldFormat

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
    formattedRows = normalize_data_and_format(get_sheet_formats_and_data(creds, "config").get('sheets', [])[0].get('data', [])[0].get('rowData', []))
    data = formattedRows[0]
    formats = formattedRows[1]
    
    res = {}
    for module_key in modules:
        res[module_key] = []

    if data:
        for rowid, row in enumerate(data):
            if len(row) == 0:
                continue
            if row[0] in res:
                res[row[0]].append(parse_row(row, modules[row[0]].get_config_params(), formats, rowid))
    return (res, formattedRows)

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
            userEnteredValue = col.get('userEnteredValue', {})
            dataVal = userEnteredValue.get('stringValue', userEnteredValue.get('formulaValue', ''))
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
def refresh_spreadsheet(creds, toUpdate, targetRange, sheetMetadata, formattedRows, appendLastLine = True):
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

    # this is a hack - the point is that it is not possible to delete all the rows; at least one needs to stay.
    # If that one row contains some data/formats, it might cause issues. Especially if that one row was meant to
    # be deleted. This way the last row of the sheet will always be empty (unless the user adds something there during the cycle, which sould not be a big deal)
    # The row can not be empty since the API would not return it in that case, so at least some value needs to be in it
    if appendLastLine:
        newValues.append(['_'])
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

def find_column_index_by_prefix(row, prefix):
    for colId, col in enumerate(row):
        if col.startswith(TIMESTAMP):
            return colId
    return -1

def add_or_replace_timestamp(row, timestamp):
    colId = find_column_index_by_prefix(row, TIMESTAMP)
    if colId == -1:
        row.append(f'{TIMESTAMP}{timestamp}')
    else:
        row[colId] = (f'{TIMESTAMP}{timestamp}')

def find_row_index(rows, key, value):
    for id, row in enumerate(rows):
        for col in row:
            if col.startswith(key):
                val = col[len(key):len(col)].strip()
                if val == value:
                    return id
    return -1

def set_timestamp_in_config(rawConfig, id, timestamp):
    data = rawConfig[1][0]
    rowIndex = find_row_index(data, ID, id)
    if rowIndex != -1:
        add_or_replace_timestamp(data[rowIndex], timestamp)

def get_sheet_formats_and_data(creds, targetRange):
    params = {'spreadsheetId': SPREADSHEET_ID,
              'ranges': targetRange,
              'fields': 'sheets(data(rowData(values(userEnteredFormat,userEnteredValue)),startColumn,startRow))'}
    return sheet(creds).get(**params).execute()

def load_data_per_tab(creds, tabs):
    currentData = {}
    for tab in tabs:
        currentData[tab] = normalize_data_and_format(get_sheet_formats_and_data(creds, tab).get('sheets', [])[0].get('data', [])[0].get('rowData', []))
    return currentData

def is_stateful(config):
    return config.get(STATEFUL, 'false') == 'true'

def find_prev_row(config, rows, id):
    data = rows[0]
    rowIndex = find_row_index(data, ID, id)
    if rowIndex == -1:
        return []
    else:
        return data[rowIndex]

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
        rawConfig = load_confg(googleCreds, plugins)
        config = rawConfig[0]
        tabs = extract_from_config(config, TAB, False)
        logging.info('Configs loaded')

        logging.info('Executing plugins')
        results = {}

        currentData = load_data_per_tab(googleCreds, tabs)
        for plugin_name in plugins:
            logging.info(f'Executing plugin {plugin_name}')
            pluginRes = {}
            for pluginConfig in config[plugin_name]:
                if pluginConfig[TAB] not in pluginRes:
                    pluginRes[pluginConfig[TAB]] = []

                if is_stateful(pluginConfig):
                    res = []
                    if TIMESTAMP in pluginConfig:
                        # has been executed already, call the plugin
                        resWithTimestamp = plugins[plugin_name].execute_stateful(
                            pluginConfig,
                            find_prev_row(pluginConfig, currentData[pluginConfig[TAB]], pluginConfig[ID]),
                            float(pluginConfig[TIMESTAMP])
                            )
                        res = resWithTimestamp[RES]
                        if len(res) > 0:
                            res.append(f'{ID}{pluginConfig[ID]}')
                        set_timestamp_in_config(rawConfig, pluginConfig[ID], resWithTimestamp[TIMESTAMP])
                    else:
                        # has never been executed, just remember the current timestamp
                        set_timestamp_in_config(rawConfig, pluginConfig[ID], datetime.timestamp(datetime.now()))
                else:
                    res = plugins[plugin_name].execute(pluginConfig)
                if len(res) != 0:
                    pluginRes[pluginConfig[TAB]].append(res)

            results[plugin_name] = pluginRes
            logging.info(f'Executed plugin {plugin_name}')

        logging.info('All plugins executed, updating output spreadsheet')
        for tab in tabs:
            toUpdate = {}
            for plugin_name in results:
                if tab in results[plugin_name]:
                    toUpdate[plugin_name] = results[plugin_name][tab]
            logging.info(f'Updating tab {tab}')
            refresh_spreadsheet(googleCreds, toUpdate, tab, sheetMetadata, currentData[tab])

        logging.info('Updating tab Config')
        refresh_spreadsheet(googleCreds, [], 'Config', sheetMetadata, rawConfig[1], False)
        logging.info(f'All tabs updated, sleeping for {timeout}s')

        break
        time.sleep(timeout)

if __name__ == '__main__':
    main()

# TODO:
# sorting of the sections
# lock the sheet while updating it
# send a notification under some conditions
# if there is exactly one BZ which satisfies the filter, the result is just "1" without the split + all etc
# add option to have WIP limits
# optimize: the sheet() does not need to be called repeatedly
# format the section titles to be prettier
# add support for conditional formatting (e.g. if the num of bugs is higher than X than make it red)
# add validations of params from the "config" tab - currently the app crashes if something is missing