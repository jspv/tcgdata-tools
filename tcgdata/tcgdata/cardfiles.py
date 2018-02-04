''' Read in the Pokémon card json files specified in the formats.json
and write them back out.
'''
import json
import argparse
import logging
import os
import sys
import re

# To be able to sort the dictionaries before writing the json
from collections import OrderedDict

logger = logging.getLogger(__name__)

# # Set log level and configure log formatter of the *root* logger
# rootlogger = logging.getLogger()
# logFormatter = logging.Formatter(
#     '%(asctime)s [%(filename)s] [%(funcName)s] [%(levelname)s] ' +
#     '[%(lineno)d] %(message)s')
# # clear existing handlers (pythonista)
# rootlogger.handlers = []
#
# # configure stream handler and add it to the root logger
# consoleHandler = logging.StreamHandler()
# consoleHandler.setFormatter(logFormatter)
# rootlogger.addHandler(consoleHandler)
# rootlogger.setLevel(args.deeploglevel)

# List to hold cards
cards = []


def main():
    # Structure to hold cards
    global cards

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_const",
                        help="increase output verbosity for local functions",
                        dest='loglevel', const=logging.INFO)
    parser.add_argument('-d', '--debug', action="store_const",
                        help="Set debug for local functions",
                        dest="loglevel", const=logging.DEBUG,
                        default=logging.WARNING)
    parser.add_argument('--carddir', nargs=1, required=True,
                        help='file to load')
    parser.add_argument('--formats', nargs=1, type=argparse.FileType('r'),
                        required=False, default='formats.json',
                        help='formats json file')
    args = parser.parse_args()

    # Set log level and configure log formatter
    logger.setLevel(args.loglevel)
    logFormatter = logging.Formatter(
        '%(asctime)s [%(filename)s] [%(funcName)s] [%(levelname)s] ' +
        '[%(lineno)d] %(message)s')

    # clear existing handlers (pythonista)
    logger.handlers = []

    # configure stream handler (this is what prints to the console)
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    logger.addHandler(consoleHandler)

    # Check the carddir
    if not os.path.isdir(args.carddir[0]):
        print('--cardir must be a directory')
        sys.exit(2)
    else:
        # Ensure there is a slash at the end of the directory
        if not args.carddir[0].endswith('/'):
            args.carddir[0] = args.carddir[0] + '/'

    # Check formats file
    if os.path.isfile(args.formats[0].name):
        formats = json.load(args.formats[0])

    cards = readfiles(args.carddir[0], formats['setfiles'])
    logger.info('Loaded {} cards'.format(len(cards)))

    # Apply filters
    for card in cards:
        sort_energy(card=card, dont_sort_energy=formats['dont_sort_energy'])
        apostrophe_to_quotes(item=card)
        # quote_to_apostrophe(item=card)
        x_to_times(item=card)
        clean_attack_text(item=card)

    writefiles(args.carddir[0], cards,
               formats['setfiles'], formats['keyorder'])


def readfiles(dirpath, setfiles):
    """ read set json files
    dirpath - folder where card files are restored
    setfiles - list of files from formats.com

    """
    # List to hold the cards
    cards = []

    if not dirpath.endswith('/'):
        dirpath = dirpath + '/'

    for setcode, setfile in setfiles.items():
        set_file_path = dirpath + setfile
        if not os.path.isfile(set_file_path):
            logger.debug('Can\'t find setfile \'{}\''.format(set_file_path))
            raise Exception('Can\'t find referenced file')
        else:
            # Open the file and load the cards
            with open(set_file_path, 'r') as set_file_handler:
                set_cards = json.load(set_file_handler)
                logger.debug('Found {} cards in {}'.format(len(set_cards),
                                                           set_file_path))
        # Add the cards to the car array
        for card in set_cards:
            cards.append(card)
    logger.debug('Loaded {} cards'.format(len(cards)))
    return cards


def writefiles(dirpath, cards, setfiles, sortorder=None):
    """ write set json files """

    # OK, time to reverse the flows
    card_output = {}
    # Initialize the structure
    for setcode in setfiles:
        card_output[setcode] = []

    # Populate cards into the right lists
    for card in cards:
        if sortorder:
            try:
                card = sortdict(card, sortorder)
            except Exception as e:
                print('Exception trying to sort card keys prior to writing')
                print('Card = {}'.format(card['id']))
                raise

        card_output[card['setCode']].append(card)

    # write the files
    for setcode, set_file_name in setfiles.items():
        print('Dumping set {} to {}'.format(setcode, set_file_name))
        with open(dirpath + set_file_name, 'w') as set_file_handler:
            print(json.dumps(card_output[setcode], indent=2,
                             ensure_ascii=False), file=set_file_handler)


def sortdict(dictionary, sortorder, prefix='.'):
    """ return an OrderedDict using the order specified in sortorder

    sortorder needs to be a list or can be a dict of lists.  If a dict, it has
    to be able to reference the list as sortorder[prefix]

    if sortorder is a list and not a dict, it will not recurse.  If it is a
    dict, it will check for dicts and lists containind dicts, and will recurse
    into them if found.

    Exception raised if there are any keys in dict which are not in
    sortorder.  When ordering dictionaries in dictionaries (recursive)
    the prefix should be passed.  (see formats.json)
    """

    # Check each value, see if it's a dict or a list containing a dict
    for key in dictionary:
        value = dictionary.get(key)

        # check if it is a l ist of dictionaries or a subdict and sortorder is
        # also a dictthen recurse
        if isinstance(sortorder, dict):
            # Build next prefix in case it's needed
            if prefix.endswith('.'):
                nextprefix = prefix + key
            else:
                nextprefix = prefix + '.' + key
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        item = sortdict(item, sortorder, prefix=nextprefix)

            # if value is a dictionary and sortorder is also a dict, recurse
            if isinstance(value, dict):
                value = sortdict(value, sortorder, prefix=nextprefix)

            # check to make sure key esists in sortorder
            if key not in sortorder[prefix]:
                raise Exception(
                    'Key {} not found in sort list'
                    ' {}'.format(key, sortorder[prefix]))
        else:
            if key not in sortorder:
                raise Exception(
                    'Key {} not found in sort list {}'.format(key, sortorder))

    # we're ready to output, if a dict, get the actual sortorder
    if isinstance(sortorder, dict):
        sortorder = sortorder[prefix]

    newdict = OrderedDict()
    # Write all the keys
    for key in sortorder:
        if key in dictionary:
            newdict[key] = dictionary[key]

    return newdict


def apostrophe_to_quotes(**kwargs):
    """ Change apostrophe to single quote characters
    replace ’s and ’t with 's and 't with

    """
    patterns = [
        (r'’s\b', r"'s"),
        (r'’t\b', r"'t")
    ]

    d = kwargs['item']
    if isinstance(d, dict):
        for k, v in list(d.items()):
            if isinstance(v, list) or isinstance(v, dict):
                apostrophe_to_quotes(item=v)
            if isinstance(v, str):
                for pattern, replacement in patterns:
                    if re.search(pattern, v):
                        logger.debug('replacing[{}]'.format(d[k]))
                        v = d[k] = re.sub(pattern, replacement, v)
                        logger.debug('replaced [{}]'.format(d[k]))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            if isinstance(v, str):
                for pattern, replacement in patterns:
                    if re.search(pattern, v):
                        logger.debug('replacing[{}]'.format(d[i]))
                        v = d[i] = re.sub(pattern, replacement, v)
                        logger.debug('replaced [{}]'.format(d[i]))
            if isinstance(v, dict):
                apostrophe_to_quotes(item=v)


def quote_to_apostrophe(**kwargs):
    """ Change single quotes to apostrophe characters
    replace 's and 't with ’s and ’t

    """
    patterns = [
        (r'\'s\b', r'’s'),
        (r'\'t\b', r'’t')
    ]

    d = kwargs['item']
    if isinstance(d, dict):
        for k, v in list(d.items()):
            if isinstance(v, list) or isinstance(v, dict):
                quote_to_apostrophe(item=v)
            if isinstance(v, str):
                for pattern, replacement in patterns:
                    if re.search(pattern, v):
                        logger.debug('replacing[{}]'.format(d[k]))
                        v = d[k] = re.sub(pattern, replacement, v)
                        logger.debug('replaced [{}]'.format(d[k]))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            if isinstance(v, str):
                for pattern, replacement in patterns:
                    if re.search(pattern, v):
                        logger.debug('replacing[{}]'.format(d[i]))
                        v = d[i] = re.sub(pattern, replacement, v)
                        logger.debug('replaced [{}]'.format(d[i]))
            if isinstance(v, dict):
                quote_to_apostrophe(item=v)


def x_to_times(**kwargs):
    """ Change where the letter x was used when it should have been \xd7

    Patterns:

    Change x to 'times' when letter x is used in x+d (e.g. x2) or d+ (e.g. 20x)
            (r'\b(\d+)x\b', r'\1×'),
            (r'\bx(\d+)\b', r'×\1')
    \b matches empty string at beginning or end of a word

    """
    patterns = [
        (r'\b(\d+)x\b', r'\1×'),
        (r'\bx(\d+)\b', r'×\1')
    ]

    d = kwargs['item']
    if isinstance(d, dict):
        for k, v in list(d.items()):
            if isinstance(v, list) or isinstance(v, dict):
                x_to_times(item=v)
            if isinstance(v, str):
                for pattern, replacement in patterns:
                    if re.search(pattern, v):
                        logger.debug('replacing[{}]'.format(d[k]))
                        v = d[k] = re.sub(pattern, replacement, v)
                        logger.debug('replaced [{}]'.format(d[k]))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            if isinstance(v, str):
                for pattern, replacement in patterns:
                    if re.search(pattern, v):
                        logger.debug('replacing[{}]'.format(d[i]))
                        v = d[i] = re.sub(pattern, replacement, v)
                        logger.debug('replaced [{}]'.format(d[i]))
            if isinstance(v, dict):
                x_to_times(item=v)


def clean_attack_text(**kwargs):
    """ Fix common errors in attack text

    Patterns:
    Change x to 'times' when letter x is used in x+d (e.g. x2) or d+ (e.g. 20x)
            (r'\b(\d+)x\b', r'\1×'),
            (r'\bx(\d+)\b', r'×\1')

    """
    patterns = [
        (r'^\(\d+×\)\s*', r''),
        (r'^\(\d+\+\)\s*', r'')
    ]

    item = kwargs['item']
    if item.get('attacks'):
        for attack in item['attacks']:
            if attack.get('text'):
                for pattern, replacement in patterns:
                    if re.search(pattern, attack['text']):
                        logger.debug('replacing[{}]'.format(attack['text']))
                        attack['text'] = re.sub(
                            pattern, replacement, attack['text'])
                        logger.debug('replaced [{}]'.format(attack['text']))


def sort_energy(**kwargs):
    """ Ensure energy costs are sorted - allows for better matching """

    def _energy_order(energytype):
        order = {
            'Free': 5,
            'Fire': 10,
            'Grass': 20,
            'Water': 30,
            'Psychic': 40,
            'Darkness': 50,
            'Fairy': 60,
            'Lightning': 70,
            'Fighting': 80,
            'Metal': 90,
            'Colorless': 100
        }
        return order[energytype]

    def _colorless_order(energytype):
        order = {
            'Free': 5,
            'Fire': 5,
            'Grass': 5,
            'Psychic': 5,
            'Darkness': 5,
            'Fairy': 5,
            'Water': 5,
            'Lightning': 5,
            'Fighting': 5,
            'Metal': 5,
            'Colorless': 100
        }
        return order[energytype]

    card = kwargs['card']
    if card.get('attacks'):
        for attack in card['attacks']:
            if attack.get('cost'):

                # Fix a few common mistakes
                for i, energy_card in enumerate(attack['cost']):
                    if energy_card == 'Green':
                        attack['cost'][i] = 'Grass'
                    if energy_card == 'Dark':
                        attack['cost'][i] = 'Darkness'

                if card['setCode'] in kwargs['dont_sort_energy']:
                    attack['cost'].sort(key=_colorless_order)
                else:
                    attack['cost'].sort(key=_energy_order)
                if attack['cost'] != ['Free']:
                    attack['convertedEnergyCost'] = len(attack['cost'])
                else:
                    attack['convertedEnergyCost'] = 0
            else:
                attack['cost'] = ['Free']
                attack['convertedEnergyCost'] = 0


if __name__ == "__main__":
    main()
