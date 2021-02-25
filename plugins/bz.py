import os.path
import logging
import sys
import requests

from common.constants import TAB, LABEL, SPLIT_BY, QUERY
from common.formatting import formatted_label_from_config

# the key in the config tab in the spreadsheet which this module represents
def get_config_key():
    return 'bz-filter'

def get_config_params():
    return [LABEL, TAB, QUERY, SPLIT_BY]

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

def execute(configs):
    apiKey = load_bz_api_key()
    res = {}
    for config in configs:
        if config[TAB] not in res:
            res[config[TAB]] = []
        label = formatted_label_from_config(config)

        headers = {'Content-Type': 'application/json', 'Accpet': 'application/json'}
        query = {
            'api_key': apiKey,
        }
        raw = requests.get(f'https://bugzilla.redhat.com/rest/bug?{config[QUERY]}', params=query, headers=headers)
        bzs = raw.json()['bugs']
        if (len(bzs) == 0):
            continue
        if (SPLIT_BY not in config):
            res[config[TAB]].append([label, f'=HYPERLINK(\"https://bugzilla.redhat.com/buglist.cgi?{config[QUERY]}\", \"{len(bzs)}\")'])
        else:
            splitBy = config[SPLIT_BY]
            values = [label, f'=HYPERLINK(\"https://bugzilla.redhat.com/buglist.cgi?{config[QUERY]}\", \"All: {len(bzs)}\")']
            res[config[TAB]].append(values)

            splitToCounts = {}
            for bz in bzs:
                if bz[splitBy] in splitToCounts:
                    splitToCounts[bz[splitBy]].append(bz['id'])
                else:
                    splitToCounts[bz[splitBy]] = [bz['id']]
            for splitToCount in splitToCounts:
                bugIds = ",".join([str(int) for int in splitToCounts[splitToCount]])
                queryUrl = f'https://bugzilla.redhat.com/buglist.cgi?f1=bug_id&o1=anyexact&query_format=advanced&v1={bugIds}'
                values.append(f'=HYPERLINK(\"{queryUrl}\", \"{splitToCount}: {len(splitToCounts[splitToCount])}\")')
    return res