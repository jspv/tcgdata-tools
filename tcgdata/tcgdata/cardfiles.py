''' Read in the Pokémon card json files specified in the formats.json
and write them back out.
'''
import json
import argparse
import logging
import os
import sys

from loadcards import sort_energy, x_to_times, quote_to_apostrophe

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

    for card in cards:
        sort_energy(item=card)

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




if __name__ == "__main__":
    main()
