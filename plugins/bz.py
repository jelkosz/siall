import os.path
import logging
import sys
import requests

from common.constants import TAB, LABEL, SPLIT_BY, QUERY, SORT
from common.formatting import formatted_label_from_config
from common.helpers import split_issues, split_array_from_config

# the key in the config tab in the spreadsheet which this module represents
def get_config_key():
    return 'bz-filter'

def get_config_params():
    return [LABEL, TAB, QUERY, SPLIT_BY, SORT]

def load_bz_api_key():
    msg = 'Problem loading bugzilla API key. Please login to bugzilla web interface, go to Preferences->API Keys, generate a new one and paste it into a file named bz.apikey next to this file.'
    if os.path.exists('bz.apikey'):
        with open('bz.apikey', 'r') as apiKey:
            key = apiKey.readline().strip()
            if key is None:
                logging.error(msg)
            # FIXME - dont return None here to crash later or at least handle later
            return key
    else:
        logging.error(msg)

def sortOutput(config):
    def actualSort(unsorted):
        if SORT not in config:
            return unsorted

        res = []
        sortedItems = split_array_from_config(config, SORT)

        # first the explicitely asked order
        for item in sortedItems:
            if item in unsorted:
                res.append(item)

        # than all the rest
        for item in unsorted:
            if item not in sortedItems:
                res.append(item)
        return res

    return actualSort

def execute(config):
    apiKey = load_bz_api_key()

    headers = {'Content-Type': 'application/json', 'Accpet': 'application/json', 'Authorization': 'Bearer ' + apiKey}
    raw = requests.get(f'https://bugzilla.redhat.com/rest/bug?{config[QUERY]}', headers=headers)
    bzs = raw.json()['bugs']

    return split_issues(
        config,
        bzs,
        f'https://bugzilla.redhat.com/buglist.cgi?{config[QUERY]}',
        lambda issues: 'https://bugzilla.redhat.com/buglist.cgi?f1=bug_id&o1=anyexact&query_format=advanced&v1=' + ",".join([str(int) for int in issues]),
        lambda bz: bz['id'],
        lambda bz, splitBy: bz[splitBy],
        sortOutput(config)
    )
    