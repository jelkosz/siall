import sys
import getopt
from functools import reduce

from jira import JIRA
import re

from common.constants import TAB, LABEL, SPLIT_BY, QUERY, ID, STATEFUL, TIMESTAMP
from common.formatting import formatted_label_from_config
from common.helpers import split_issues

# dependencies:
# basic
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

def load_issues(config):
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

    jira = JIRA(server=JIRA_BASE_URL, auth=(user, passwd))
    return jira.search_issues(config[QUERY], maxResults=config[MAX_RESULTS])

def execute(config):
    issues = load_issues(config)

    return split_issues(
        config,
        issues,
        f'{JIRA_BASE_URL}/issues/?jql={config[QUERY]}',
        create_query,
        lambda issue: issue.key,
        rgetattr)

def execute_stateful(config, prevRow, timestamp):
    issues = load_issues(config)
    return ['Z']
