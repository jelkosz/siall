# a file of various helper functions used by the plugins

from common.formatting import formatted_label_from_config
from common.constants import SPLIT_BY


def split_issues(config, issues, linkToAll, createIssueQuery, extractKey, extractVal):
    if len(issues) == 0:
        return []

    label = formatted_label_from_config(config)
    if SPLIT_BY not in config:
        return [label, f'=HYPERLINK(\"{linkToAll}\", \"{len(issues)}\")']
    
    splitBy = config[SPLIT_BY]
    values = [label, f'=HYPERLINK(\"{linkToAll}\", \"All: {len(issues)}\")']

    splitToCounts = {}
    for issue in issues:
        val = extractVal(issue, splitBy)
        if val in splitToCounts:
            splitToCounts[val].append(extractKey(issue))
        else:
            splitToCounts[val] = [extractKey(issue)]
    
    for splitToCount in splitToCounts:
        queryUrl = createIssueQuery(splitToCounts[splitToCount])
        values.append(f'=HYPERLINK(\"{queryUrl}\", \"{splitToCount}: {len(splitToCounts[splitToCount])}\")')
    
    return values