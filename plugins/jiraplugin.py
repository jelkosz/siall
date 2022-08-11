import sys
import getopt
from datetime import datetime
import time
import dateutil.parser
from functools import reduce

from jira import JIRA
import re

from common.constants import TAB, LABEL, SPLIT_BY, QUERY, ID, STATEFUL, TIMESTAMP, RES, IGNORE_FIELDS, RESTRICT_TIME, MENTIONS, SPLIT
from common.formatting import formatted_label_from_config
from common.helpers import split_issues, split_array_from_config

# dependencies:
# pip install jira

MAX_RESULTS = 'maxResults:'
JIRA_BASE_URL = 'https://issues.redhat.com'

def get_config_key():
    return 'jira-filter'

def get_config_params():
    return [LABEL, TAB, QUERY, SPLIT_BY, MAX_RESULTS, IGNORE_FIELDS, MENTIONS, ID, STATEFUL, RESTRICT_TIME, TIMESTAMP, SPLIT]

# for example fields.status.name
def rgetattr(obj, attr, *args):
    def _getattr(obj, attr):
        if obj is None:
            return ''
        return getattr(obj, attr, *args)
    return reduce(_getattr, [obj] + attr.split('.'))

def escape_query(query):
    return query.replace('"', '""')

def create_query(issueIds):
    baseJql = f'{JIRA_BASE_URL}/issues/?jql='
    issuesJql = ''
    for i, issueId in enumerate(issueIds):
        if i != len(issueIds) - 1:
            issuesJql = issuesJql + f'key={issueId} or '
        else:
            issuesJql = issuesJql + f'key={issueId}'
    return f'{baseJql}{escape_query(issuesJql)}'

def init_jira():
    try:
        opts, args = getopt.getopt(sys.argv[1:], "", ["jiratoken="])
    except getopt.GetoptError:
        print('Jira credentials not provided, ignoring plugin. In order to execute the jira plugin, please run the python main.py --jiratoken <jira token>')
        return []

    for opt, arg in opts:
      if opt in ("--jiratoken"):
        jiratoken = arg
    for _ in range(3):
        try:
            return JIRA(server=JIRA_BASE_URL, token_auth=jiratoken)
        except:
            # jira likes to fail from time to time and next time it passes. Lets try 3 times
            print('longin to jira failed, trying again in 2 seconds')
            time.sleep(2)


def execute(config):
    issues = init_jira().search_issues(config[QUERY], maxResults=config[MAX_RESULTS])

    return split_issues(
        config,
        issues,
        f'{JIRA_BASE_URL}/issues/?jql={escape_query(config[QUERY])}',
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
    ignoreFields = split_array_from_config(config, IGNORE_FIELDS)
    mentionsFields = split_array_from_config(config,MENTIONS)
    restrictTime = config.get(RESTRICT_TIME, 'updated')
    split = config.get(SPLIT, 'true')

    fieldToListOfChanges = parse_prev_row(prevRow)
    jql = config[QUERY]
    if len(jql.strip()) > 0:
        jql = jql + ' and '
    jql = f'{jql}{restrictTime} > "{to_query_time(lastExecutedTs)}"'

    # todo: if the "split" is false, the exapands here are not needed
    issues = init_jira().search_issues(jql, maxResults=config[MAX_RESULTS], expand='changelog', fields = 'comment')
    lastTimestampFromResults = lastExecutedTs


    if split == 'false':
        fieldToListOfChanges['all'] = []
        for issue in issues:
            for history in issue.changelog.histories:
                ts = to_timestamp(history.created)
                if ts > lastTimestampFromResults:
                    lastTimestampFromResults = ts
            fieldToListOfChanges['all'].append(issue.key)
    else:
        for issue in issues:
            for history in issue.changelog.histories:
                ts = to_timestamp(history.created)
                if ts <= lastExecutedTs:
                    # something has changed on this issue (otherwise it would not be loaded) but this particular change happend before the last time this has been executed
                    # so no need to show it
                    continue
                if ts > lastTimestampFromResults:
                    lastTimestampFromResults = ts
                for item in history.items:
                    f = item.field
                    if f in ignoreFields:
                        continue
                    if f not in fieldToListOfChanges:
                        fieldToListOfChanges[f] = []
                    if issue.key not in fieldToListOfChanges[f]:
                        fieldToListOfChanges[f].append(issue.key)

            mention = 'mention'
            if mention not in ignoreFields and len(mentionsFields) > 0:
                for c in issue.fields.comment.comments:
                    if to_timestamp(c.created) <= lastExecutedTs:
                        # too old, skip...
                        continue
                    for mentionsField in mentionsFields:
                        mentionKey = f'{mentionsField} mentioned'
                        if mentionKey not in fieldToListOfChanges:
                            fieldToListOfChanges[mentionKey] = []
                        if f'[~{mentionsField}]' in c.body:
                            if issue.key not in fieldToListOfChanges[mentionKey]:
                                fieldToListOfChanges[mentionKey].append(issue.key)

    res = []
    if len(fieldToListOfChanges) > 0:
        res.append(formatted_label_from_config(config))
    for field in fieldToListOfChanges:
        if len(fieldToListOfChanges[field]) == 0:
            continue
        linkWithCount = f'=HYPERLINK("{create_query(fieldToListOfChanges[field])}", "{field}: " & COUNTA({format_list_of_jira_keys(fieldToListOfChanges[field])}))'
        res.append(linkWithCount)

    return {TIMESTAMP: lastTimestampFromResults, RES: res}