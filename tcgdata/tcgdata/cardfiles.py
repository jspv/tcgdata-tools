''' Read in the Pokémon card json files specified in the formats.json
and write them back out.
'''
import json
import argparse
import logging
import os
import sys
import tcgdata.cardfilters as cardfilters
import verbosity

# To be able to sort the dictionaries before writing the json
from collections import OrderedDict

# Initialise the logger
logger = logging.getLogger(__name__)

# List to hold cards
cards = []


def main():
    # Structure to hold cards
    global cards

    parser = argparse.ArgumentParser(description='Normalize TCG json files')
    parser.add_argument('--carddir', nargs=1, required=True,
                        help='directory of the files to read and write')
    parser.add_argument('--formats', nargs='?', type=argparse.FileType('r'),
                        required=False, default='formats.json',
                        help='formats json file')

    # add logging arguments
    verbosity.add_arguments(parser)
    args = parser.parse_args()

    # initialize logging handle logging arguments
    verbosity.initialize(logger)
    verbosity.handle_arguments(args, logger)

    #
    # Prep done, start the work
    #

    # Check the carddir
    if not os.path.isdir(args.carddir[0]):
        print('--cardir must be a directory')
        sys.exit(2)
    else:
        # Ensure there is a slash at the end of the directory
        if not args.carddir[0].endswith('/'):
            args.carddir[0] = args.carddir[0] + '/'

    # Check formats file
    print(args.formats)
    if os.path.isfile(args.formats.name):
        formats = json.load(args.formats)
        logger.info('Loaded formats file {}'.format(args.formats.name))

    logger.info('Loading files in: {}'.format(args.carddir[0]))
    cards = readfiles(args.carddir[0], formats['setfiles'])
    logger.info('Loaded {} cards'.format(len(cards)))

    # Apply filters
    for card in cards:
        cardfilters.sort_energy(
            card=card, dont_sort_energy=formats['dont_sort_energy'])
        cardfilters.apostrophe_to_quotes(item=card)
        # quote_to_apostrophe(item=card)
        cardfilters.x_to_times(item=card)
        cardfilters.clean_attack_text(item=card)
        cardfilters.add_converted_reteat_cost(card=card)

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
                logger.debug('Reading {}'.format(set_file_path))
                set_cards = json.load(set_file_handler)
                logger.debug('Found {} cards in {}'.format(len(set_cards),
                                                           set_file_path))
        # Add the cards to the car array
        for card in set_cards:
            cards.append(card)
    logger.info('Loaded {} cards'.format(len(cards)))
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


if __name__ == "__main__":
    main()
