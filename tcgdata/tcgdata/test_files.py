''' Read in the Pokémon card json files specified in the formats.json
and write them back out.  This is purely a sanity check to make sure the
files are in a standardized format
'''
import json
import argparse
import logging
import os
import sys

# Note: not using OrderedDict, but leaving remenants of it here in cardset
# I need to add it back in
# from collections import OrderedDict


def main():

    # List to hold the cards
    cards = []

    parser = argparse.ArgumentParser()
    parser.add_argument('--carddir', nargs=1, required=True,
                        help='file to load')
    parser.add_argument('--formats', nargs=1, type=argparse.FileType('r'),
                        required=True, help='formats json file')
    args = parser.parse_args()

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

    for setcode, setfile in formats['setfiles'].items():
        print('setcode = {}, setfile={}'.format(setcode, setfile))
        set_file_path = args.carddir[0] + setfile
        if not os.path.isfile(set_file_path):
            print('Can\'t find setfile \'{}\''.format(set_file_path))
            sys.exit(2)
        else:
            with open(set_file_path, 'r') as set_file_handler:
                set_cards = json.load(set_file_handler)
                print('Found {} cards in {}'.format(len(set_cards),
                                                    set_file_path))
        for card in set_cards:
            cards.append(card)

    print('Loaded {} cards'.format(len(cards)))

    # OK, time to reverse the flows
    card_output = {}
    # Initialize the structure
    for setcode in formats['setfiles']:
        card_output[setcode] = []

    # Populate cards into the right lists
    for card in cards:
        card_output[card['setCode']].append(card)

    # write the files
    for setcode, set_file_name in formats['setfiles'].items():
        print('Dumping set {} to {}'.format(setcode, set_file_name))
        with open(args.carddir[0] + set_file_name, 'w') as set_file_handler:
            print(json.dumps(card_output[setcode], indent=2,
                             ensure_ascii=False), file=set_file_handler)

    # setdata = json.load(args.file[0], object_pairs_hook=OrderedDict)
    # setdata = json.load(args.file[0])

    # for card in setdata:
    # if card.get('name') == "Kakuna":
    #     card['name'] = "Mimikyu"
    #     card['newthing'] = "foo"

    # print(json.dumps(setdata, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
