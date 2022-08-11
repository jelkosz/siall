# prod
SPREADSHEET_ID = '1JAZXnfmyx8yQ3yeBcKORfMn9sGot-VzWPHUVPJRhPNg'

# dev
# SPREADSHEET_ID = '1vXVGYBpR4szN5zcee15GBoXKfpqFwG9A82yp2szYdnU'

# PUBLIC PARAMETERS
# generic parameters
# label: the label printed next to it
LABEL = 'label:'
# tab: the tab to which it will be printed
TAB = 'tab:'
# query: filter query it has to satisfy
QUERY = 'query:'
STATUS_SUCCESS = 'Success'
STATUS_ERROR = 'ERROR'
# bugzilla specific parameters
# how the result should be split (e.g. by status/priority/severity)
SPLIT_BY = 'splitBy:'

# short the results in this order
SORT = 'sort:'
# INTERNAL CONSTANTS
# Section of output
SECTION = 'section:'
RAW_ROW = 'rawRow'

ID = 'id:'
TIMESTAMP = 'lastExecutedTimestamp:'
STATEFUL = 'stateful:'
RES = 'res:'

# stateful jira
IGNORE_FIELDS = 'ignoreFields:'
MENTIONS = 'mentions:'
# when tracking changes, the changes are always tracked since some time.
# For example,
#   if you want to see issues which has changed since the last time you've checked, use: restrictTime: updated
#   if you want to see issues which has been created since the last time you've checked, use: restrictTime: created
# default is updated
RESTRICT_TIME = 'restrictTime:'
SPLIT = 'split:'