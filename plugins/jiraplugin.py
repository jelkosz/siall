import sys
import getopt
from datetime import datetime
import dateutil.parser
from functools import reduce

from jira import JIRA
import re

from common.constants import TAB, LABEL, SPLIT_BY, QUERY, ID, STATEFUL, TIMESTAMP, RES
from common.formatting import formatted_label_from_config
from common.helpers import split_issues

# dependencies:
# pip install jira

MAX_RESULTS = 'maxResults:'
JIRA_BASE_URL = 'https://issues.redhat.com'

def get_config_key():
    return 'jira-filter'

def get_config_params():
    return [LABEL, TAB, QUERY, SPLIT_BY, MAX_RESULTS, ID, STATEFUL, TIMESTAMP]

def rgetattr(obj, attr, *args):
    def _getattr(obj, attr):
        if obj is None:
            return ''
        return getattr(obj, attr, *args)
    return reduce(_getattr, [obj] + attr.split('.'))

def create_query(issueIds):
    baseJql = f'{JIRA_BASE_URL}/issues/?jql='
    issuesJql = ''
    for i, issueId in enumerate(issueIds):
        if i != len(issueIds) - 1:
            issuesJql = issuesJql + f'key={issueId} or '
        else:
            issuesJql = issuesJql + f'key={issueId}'

    return f'{baseJql}{issuesJql}'

def init_jira():
    try:
        opts, args = getopt.getopt(sys.argv[1:], "", ["jirauser=", "jirapass="])
    except getopt.GetoptError:
        print('Jira credentials not provided, ignoring plugin. In order to execute the jira plugin, please run the python main.py --jirauser <jira user name> --jirapass <jira password>')
        return []

    for opt, arg in opts:
      if opt in ("--jirauser"):
        user = arg
      elif opt in ("--jirapass"):
        passwd = arg

    return JIRA(server=JIRA_BASE_URL, auth=(user, passwd))

def execute(config):
    issues = init_jira().search_issues(config[QUERY], maxResults=config[MAX_RESULTS])

    return split_issues(
        config,
        issues,
        f'{JIRA_BASE_URL}/issues/?jql={config[QUERY]}',
        create_query,
        lambda issue: issue.key,
        rgetattr)

def to_timestamp(str):
    dt = dateutil.parser.parse(str)
    return datetime.timestamp(dt)

# Converts a float timestamp to a sting which can be used as a JQL param
def to_query_time(timestamp):
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y/%m/%d %H:%M")

def format_list_of_jira_keys(keys):
    res = ''
    for key in keys:
        res = res + f'"{create_query([key])}", '

    return res

def parse_prev_row(prevRows):
    r = r'.*=HYPERLINK.*, "(.*): " \& COUNTA\((.*), \)\)'
    res = {}
    for row in prevRows:
        mo = re.match(r, row, re.S | re.I)
        if mo:
            issueType = mo.group(1)
            issues = mo.group(2).split(', ')

            if issueType not in res:
                res[issueType] = []

            for issue in issues:
                # dont want to use a regex here since this is way faster
                issueKey = issue[len(JIRA_BASE_URL + '/issues/?jql=key=') + 1: len(issue) - 1]
                res[issueType].append(issueKey)

    return res

def execute_stateful(config, prevRow, lastExecutedTs):
    fieldToListOfChanges = parse_prev_row(prevRow)
    jql = f'{config[QUERY]} and updated > "{to_query_time(lastExecutedTs)}"'
    issues = init_jira().search_issues(jql, maxResults=config[MAX_RESULTS], expand='changelog')
    lastTimestampFromResults = lastExecutedTs

    for issue in issues:
        for i, history in enumerate(issue.changelog.histories):
            ts = to_timestamp(history.created)
            if ts <= lastExecutedTs:
                # something has changed on this issue (otherwise it would not be loaded) but this particular change happend before the last time this has been executed
                # so no need to show it
                continue
            if ts > lastTimestampFromResults:
                lastTimestampFromResults = ts
            for item in history.items:
                f = item.field
                if f not in fieldToListOfChanges:
                    fieldToListOfChanges[f] = []
                if issue.key not in fieldToListOfChanges[f]:
                    fieldToListOfChanges[f].append(issue.key)

    res = []
    if len(fieldToListOfChanges) > 0:
        res.append(formatted_label_from_config(config))
    for field in fieldToListOfChanges:
        linkWithCount = f'=HYPERLINK("{create_query(fieldToListOfChanges[field])}", "{field}: " & COUNTA({format_list_of_jira_keys(fieldToListOfChanges[field])}))'
        res.append(linkWithCount)

    return {TIMESTAMP: lastTimestampFromResults, RES: res}