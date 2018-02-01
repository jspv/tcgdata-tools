''' Read in the Pokémon card json files specified in the formats.json
and write them back out.
'''
import json
import argparse
import logging
import os
import sys
import re

from loadcards import x_to_times, quote_to_apostrophe

# Note: not using OrderedDict, but leaving remenants of it here in cardset
# I need to add it back in
# from collections import OrderedDict

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
                        required=True, help='formats json file')
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
        # sort_energy(card=card, dont_sort_energy=formats['dont_sort_energy'])
        apostrophe_to_quotes(item=card)

    writefiles(args.carddir[0], cards, formats['setfiles'])


def readfiles(dirpath, setfiles):
    """ read set json files """
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


def writefiles(dirpath, cards, setfiles):
    """ write set json files """

    # OK, time to reverse the flows
    card_output = {}
    # Initialize the structure
    for setcode in setfiles:
        card_output[setcode] = []

    # Populate cards into the right lists
    for card in cards:
        card_output[card['setCode']].append(card)

    # write the files
    for setcode, set_file_name in setfiles.items():
        print('Dumping set {} to {}'.format(setcode, set_file_name))
        with open(dirpath + set_file_name, 'w') as set_file_handler:
            print(json.dumps(card_output[setcode], indent=2,
                             ensure_ascii=False), file=set_file_handler)


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

                # # Check to see if a multi-type attack (debugging)
                # energy_set = set(attack['cost'])
                # energy_set.discard('Colorless')
                # if len(energy_set) > 1:
                #     print('CardId = {} in set {}'.format(card['id'], card['set']))

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
