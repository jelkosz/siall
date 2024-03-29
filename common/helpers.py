# a file of various helper functions used by the plugins

from common.formatting import formatted_label_from_config
from common.constants import SPLIT_BY

# gets the config and what key to look for in it. Expects to find either a comma separated list of strings in it or nothing.
# If it finds nothing, it returns an empty list.
# If it finds a comma separated list of items, it returns an array of this items with empty strings removed
def split_array_from_config(config, key):
    return list(filter(lambda item: item, config.get(key, '').split(',')))

def split_issues(config, issues, linkToAll, createIssueQuery, extractKey, extractVal, sortKeys = None):
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
        if isinstance(val, list):
            strvals = []
            for strval in val:
                if isinstance(strval, str):
                    strvals.append(strval)
                elif hasattr(strval, 'name'):
                    strvals.append(strval.name)
                else:
                    strvals.append(str(strval))
            val = ", ".join(strvals)
        if val in splitToCounts:
            splitToCounts[val].append(extractKey(issue))
        else:
            splitToCounts[val] = [extractKey(issue)]
    
    sortedKeys = splitToCounts.keys()
    if sortKeys is not None:
        sortedKeys = sortKeys(splitToCounts.keys())

    for splitToCount in sortedKeys:
        queryUrl = createIssueQuery(splitToCounts[splitToCount])
        values.append(f'=HYPERLINK(\"{queryUrl}\", \"{splitToCount}: {len(splitToCounts[splitToCount])}\")')
    
    return values