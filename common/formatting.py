from common.constants import LABEL

def boldFormat(bold):
    return [{'userEnteredFormat': {'textFormat': {'bold': bold}}}]

def sectionFormat():
    return [
        {'userEnteredFormat': {
            'textFormat': {'bold': True},
            'backgroundColorStyle': {'rgbColor': {'red': 0.7176471, 'green': 0.7176471, 'blue': 0.7176471}}
            }}
        ]

def formatted_label_from_config(config):
    labelValue = config[LABEL]
    labelFormat = config.get(LABEL + '-format', None)

    if labelFormat is None:
        return labelValue
    else:
        return {'value': labelValue, 'format': labelFormat}