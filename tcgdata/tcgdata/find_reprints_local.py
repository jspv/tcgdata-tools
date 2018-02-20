''' Search through database and detect reprints '''
import builtins
import os
import boto3
import json
import argparse
import sys
import logging
import pickle
import re
import copy
from fuzzywuzzy import fuzz

from tcgdata.forms import Form, create_compare_form
from tcgdata.forms import display_cards, review_cards_manually
from tcgdata.cardfiles import readfiles, writefiles
import pylogging

logger = logging.getLogger(__name__)

# Nasty Globals
errorlist = []
nomatchlist = {}
forcematchlist = {}
reprintslist = []


# Create custom exception for when Quit is chosen on the gui
class QuitChosen(Exception):
    pass


def main():
    # ensure we use the global errorlist
    global errorlist
    global nomatchlist
    global forcematchlist
    global reprintlist

    parser = argparse.ArgumentParser()
    parser.add_argument('--hard', action='store_true',
                        help='find hard matches', required=False)
    parser.add_argument('--easy', '-e', action='store_true',
                        help='find easy matches only', required=False)
    parser.add_argument('--carddir', required=True,
                        help='file to load')
    parser.add_argument('--reprintsfile', default='reprints.json',
                        required=False, help='output reprints to file')
    parser.add_argument('--startindex', type=int, required=False,
                        help='force start at a specified index (dangerous)')
    parser.add_argument('--forcematchfile', default='forced.json',
                        help='known reprints with negligible differences')
    parser.add_argument('--errorfile', default='errors.json',
                        help='override errorfile.json file')
    parser.add_argument('--nomatchfile', default='nomatches.json',
                        help='override nomatches.json file')
    parser.add_argument('--formatsfile', type=argparse.FileType('r'),
                        required=False, default='formats.json',
                        help='formats json file')

    # add logging arguments
    pylogging.add_arguments(parser)
    args = parser.parse_args()

    # initialize logging handle logging arguments
    pylogging.initialize(logger)
    pylogging.handle_arguments(args, logger=logger)

    if args.hard and args.easy:
        parser.error("--easy and --hard are mutually exclusive")
        sys.exit(2)
    if not (args.hard or args.easy):
        parser.error("--easy or --hard required")
        sys.exit(2)
    if args.startindex and not args.reprintsfile:
        parser.error("--startindex requires --reprintfile")
        sys.exit(2)
    if args.startindex and not os.path.isfile(args.reprintsfile):
        parser.error(
            'reprintsfile \'{}\' must exist in order to use '
            '--startindex'.format(args.reprintsfile))
        sys.exit(2)

    is_easymode = True if args.easy else False

    # Check the carddir
    if not os.path.isdir(args.carddir):
        print('--cardir must be a directory')
        sys.exit(2)
    else:
        # Ensure there is a slash at the end of the directory
        if not args.carddir.endswith('/'):
            args.carddir = args.carddir + '/'

    # Check formats file
    if os.path.isfile(args.formatsfile.name):
        formats = json.load(args.formatsfile)
        logger.info('Loaded formats file {}'.format(args.formatsfile.name))

    # Load the cards
    logger.info('Reading cards from {}'.format(args.carddir))
    cards = readfiles(args.carddir, formats['setfiles'])

    # initialise errorlist - if the file exists, load the json files
    if args.errorfile and os.path.isfile(args.errorfile):
        logger.info('Loading and processing errorfile '
                    '{}'.format(args.errorfile))
        with open(args.errorfile, 'r') as errorfile:
            errorlist = json.load(errorfile)
            for error in errorlist:
                for cardid, errorstruct in error.items():
                    # use generator exporession to find the right card,
                    # if cardid is not Found then None is returned
                    card = next(
                        (card for card in cards if card['id'] == cardid), None)
                    if card is None:
                        raise Exception(
                            'Cant find cardid={} loading errorfile')
                    # Check to see if the error still exists, if so, apply
                    # the edit
                    check_val = _get_val(
                        card,
                        errorstruct['key'])[errorstruct['index']]
                    if (check_val == errorstruct['oldvalue']):
                        _put_val(card, errorstruct['key'],
                                 errorstruct['index'], errorstruct['newvalue'])
                        logger.debug('Fixed error: {} - {}'.format(
                            card['id'], errorstruct['key']))
                    else:
                        logger.debug('Oldvalue does not match current value '
                                     'not applying edit.\n'
                                     'D: card = {}\n'
                                     'D: key = {}\n'
                                     'D: current = {}\n'
                                     'D: oldvalue = {}\n'
                                     'D: newvalue '
                                     '= {}'.format(card['id'],
                                                   errorstruct['key'],
                                                   check_val,
                                                   errorstruct['oldvalue'],
                                                   errorstruct['newvalue']))
                        if check_val == errorstruct['newvalue']:
                            logger.debug('Error already fixed: error: {} - {}'
                                         ''.format(card['id'],
                                                   errorstruct['key']))
                            logger.debug('Removing the error')
                            _delete_error(card, errorstruct['key'],
                                          errorstruct['index'])
                        else:
                            # Bad state, force the error and exit
                            print('Oldvalue does not match current value '
                                  'not applying edit.\ncard = {}\n'
                                  'key = {}\ncurrent = {}\n'
                                  'oldvalue = {}\nnewvalue '
                                  '= {}'.format(card['id'],
                                                errorstruct['key'],
                                                check_val,
                                                errorstruct['oldvalue'],
                                                errorstruct['newvalue']))
                            sys.exit(2)

    # initialise nomatchfile - if the file exists, load the json
    if args.nomatchfile and os.path.isfile(args.nomatchfile):
        with open(args.nomatchfile, 'r') as nomatchfile:
            nomatchlist = json.load(nomatchfile)
            logger.info('Loaded nomatchfile {}'.format(args.nomatchfile))

    # initialize forcematchfile - if the file exists, load the json
    if args.forcematchfile and os.path.isfile(args.forcematchfile):
        with open(args.forcematchfile, 'r') as forcematchfile:
            forcematchlist = json.load(forcematchfile)
            logger.debug('Loaded forcematchfile {}'.format(
                args.forcematchfile))

    # initilalize reprintsfile - used for --startindex (existance is checked)
    # earlier
    if args.startindex:
        with open(args.reprintsfile, 'r') as reprintsfile:
            reprintslist = json.load(reprintsfile)
            logger.info('Loaded reprintsfile {}'.format(args.reprintsfile))

    # Find the reprints
    with open(args.reprintsfile, 'w') as reprintsfile:
        if args.startindex:
            logger.info('Processing at index {}'.format(args.startinex))
            print(find_all_reprints(cards, is_easymode, args.startindex),
                  file=reprintsfile)
        else:
            print(find_all_reprints(cards, is_easymode), file=reprintsfile)

    # write the errorfile
    if len(errorlist):
        with open(args.errorfile, 'w') as errorfile:
            # logger.debug('errorlist = {}'.format(errorlist))
            print(json.dumps(errorlist, indent=4), file=errorfile)

    # write the nomatchfile
    # {cardid: [cardid, cardid, carddid], cardid: [...]}
    if len(nomatchlist):
        with open(args.nomatchfile, 'w') as nomatchfile:
            logger.debug('nomatchlist = {}'.format(nomatchlist))
            print(json.dumps(nomatchlist, indent=4), file=nomatchfile)

    # write the forcematchfile
    if len(forcematchlist):
        with open(args.forcematchfile, 'w') as forcematchfile:
            logger.debug('forcematchlist = {}'.format(forcematchlist))
            print(json.dumps(forcematchlist, indent=4), file=forcematchfile)

    # finally, write the cardfiles
    writefiles(args.carddir, cards,
               formats['setfiles'], formats['keyorder'])


def find_all_reprints(cards, is_easymode, startindex=0):
    """ Search through a list of card objects and find all reprints """

    # holder for list of reprints in the format of:
    #   [{Name:[cardid, cardid]}, {Name:[cardid, cardid, cardid]}]
    #  reprintslist = []  (now a global

    # Use an index i so that we can pass the current index to the
    # find_reprints_x function indicating where to start the search from.
    # cards prior to i would have been checked already.
    for i, card in enumerate(cards):

        # if startindex specified, shortcut to that index
        if i < startindex:
            continue

        supertype = card['supertype']

        if supertype in ['Pokémon', 'Trainer']:

            # if there are any reprint objects in the reprintslist, check to
            # see if the current card is already listed in any of them, if not
            # then go ahead and search for reprints.
            # below code loops through all current items in reprintslist,
            #   sees if the name of the current card matches the key, looks
            #   through the values to see if the card is already
            #   the list  If so, then this card is an already known
            #   reprint, no need to go further.
            # reminder:
            #   reprintlist is in the format of:
            #   [{Name:[cardid, cardid]}, {Name:[cardid, cardid, cardid]}]

            if not any(card['id'] in prints.get(card['name'], {})
                       for prints in reprintslist):
                # output the index so we can follow the progress
                print(i, supertype, card['name'])
                try:
                    reprints = find_card_reprints(i, cards, is_easymode)
                    if reprints:
                        reprintslist.append(reprints)
                        print(json.dumps(reprints))
                except QuitChosen as e:
                    print('Quit chosen Exiting cleaning saving file')
                    print('Exception was {}'.format(e))
                    return(json.dumps(reprintslist, indent=4))

    return(json.dumps(reprintslist, indent=4))


def find_card_reprints(index, cards, find_easy=False):
    """ identify reprints for a specific pokemon card, return a dictionary
        in the form of {Name: [cardid, cardid]}
    """
    compare_response = {}
    reprintdict = {}
    card1 = cards[index]
    if find_easy:
        # check each card starting from the next card in the index, it is
        # presumed that the earlier cards have already been checked.
        for k in range(index + 1, len(cards)):
            card2 = cards[k]
            if compare_cards_easy(card1, card2)['matchlevel'] == 1:
                if len(reprintdict) == 0:
                    reprintdict[card1['name']] = [card1['id']]
                reprintdict[card1['name']].append(card2['id'])

        if reprintdict:
            return(reprintdict)
        return None

    # It's a detailed/fuzzy search (hard)
    for k in range(index + 1, len(cards)):
        card2 = cards[k]

        # first check the nomatches dictionary, if the cards are there, we
        # already know they don't match - so move along
        if (card1['id'] in nomatchlist and
                card2['id'] in nomatchlist[card1['id']]):
            continue

        # now check the forcematches dictionary, if the cards are there,
        # we know they need to match
        if (card1['id'] in forcematchlist and
                card2['id'] in forcematchlist[card1['id']]):
            compare_response['matchlevel'] = 1
            compare_response['mismatch_fields'] = None
        else:
            try:
                compare_response = compare_cards_full(card1, card2)
            # catch all exeptions, print cards and reraise
            except Exception as e:
                print('Exception caught running compare_cards_full')
                print('\n\ncard1=\n{}\n\ncard2=\n{}\n\n'.format(card1, card2))
                raise

        # matchlevel of 1 means possible match
        if (compare_response['matchlevel'] == 1 and
                compare_response.get('mismatch_fields') is not None):
            logger.info('{!a}'.format(compare_response))
            # print(pickle.dumps(card1), '\n\n', pickle.dumps(card2),
            #       '\n\n',  pickle.dumps(compare_response['mismatch_fields']))

            # Send the cards off for manual review of the picture
            # return struct = {
            # 'matched' : True, False 'Quit' or 'Error'
            # 'forcematch': [id, id]
            # 'errors': [{'id': cardid,
            #             'field': field_to_fix,
            #             'index': index_in_field,
            #             'newvalue': new_text},]}
            manual_reviewstatus = review_cards_manually(
                card1, card2, compare_response['mismatch_fields'])
            logger.debug('Return from review_cards_manually = {}'.format(
                manual_reviewstatus))

            # If forcematch was set, add it to the forcematchlist
            if manual_reviewstatus.get('forcematch') is not None:
                # logger.debug('type of forcematchlist is {}'.format(
                #     type(forcematchlist)))
                # logger.debug(forcematchlist)
                if card1['id'] in forcematchlist:
                    forcematchlist[card1['id']].append(card2['id'])
                else:
                    forcematchlist[card1['id']] = [card2['id']]
                if card2['id'] in forcematchlist:
                    forcematchlist[card2['id']].append(card1['id'])
                else:
                    forcematchlist[card2['id']] = [card1['id']]

            # if one of the cards matched the picture, mark the cards as
            # matched, fix the error, and update the reprintslist
            if manual_reviewstatus['matched'] == 'True':
                # Write the errors to the error file and apply them to the
                # cards in memory.  Errors is a list of 2 key/value dicts
                for error in manual_reviewstatus['errors']:
                    logger.debug('card to fix = {}'.format(error['id']))
                    logger.debug('field to fix = {}'.format(error['field']))
                    logger.debug('new entry = {}'.format(error['newvalue']))
                    # Check if card1 matches the error
                    if card1['id'] == error['id']:
                        # logging.debug('original\n{}'.format(card1))
                        _save_error(card1,
                                    error['field'],
                                    error['index'],
                                    error['newvalue'])
                        _put_val(card1,
                                 error['field'],
                                 error['index'],
                                 error['newvalue'])
                    # the error is in card2
                    else:
                        # logger.debug('original\n{}'.format(card2))
                        _save_error(card2,
                                    error['field'],
                                    error['index'],
                                    error['newvalue'])
                        _put_val(card2,
                                 error['field'],
                                 error['index'],
                                 error['newvalue'])
                        # logger.debug('revised\n{}'.format(card2))

            # Manual review says *no match*
            elif manual_reviewstatus['matched'] == 'False':
                # set the compare_response as a solid "no" and append to the
                # nomatchlist dict (value is a list of cardids) so we can
                # ignore these in the future
                compare_response['matchlevel'] = 0
                if card1['id'] in nomatchlist:
                    nomatchlist[card1['id']].append(card2['id'])
                else:
                    nomatchlist[card1['id']] = [card2['id']]
                if card2['id'] in nomatchlist:
                    nomatchlist[card2['id']].append(card1['id'])
                else:
                    nomatchlist[card2['id']] = [card1['id']]

            # Abort early if quit was chosen
            elif manual_reviewstatus['matched'] == 'Quit':
                raise QuitChosen

            # Should never get here, abort
            else:
                raise Exception('Bad manual_reviewstatus')

        # if matched, add to reprints list
        # reprints is an list of [{key:[list]}] pairs where each key is
        # a card name.  Note: there may be multiple entries with thee
        # same card name
        if (compare_response['matchlevel'] == 1):
            if len(reprintdict) == 0:
                reprintdict[card1['name']] = [card1['id']]
            reprintdict[card1['name']].append(card2['id'])

            # return(reprintslist)

    if reprintdict:
        return reprintdict


def compare_cards_easy(card1, card2):
    """ Compare two pokémon cards

    Return structure: {matchlevel: [-1|0|1]}
                          -1 = not supported
                           0 = not a full match of checked value
                           1 = full match of checked values
    """
    QUICKFAIL = {'matchlevel': 0}
    QUICKPASS = {'matchlevel': 1}
    NONSUPPORTED = {'matchlevel': -1}

    # If it's not a pokemon, continue (TODO - add more comparisons)
    if card1['supertype'] != card2['supertype']:
        return QUICKFAIL

    if card1['supertype'] != 'Pokémon' and card1['supertype'] != 'Trainer':
        return NONSUPPORTED

    # TODO - change conditional when supporing more types, here now for
    # indent management
    if card1['supertype'] == 'Pokémon':

        # Note: checks are done in order
        checks = {'hp': 'match',
                  'name': 99,
                  'text': 'match',
                  'attacks': 'count',
                  'attacks.name': 'match',
                  'attacks.text': 'match',
                  'attacks.damage': 'match',
                  'attacks.cost': 'match',
                  'attacks.convertedEnergyCost': 'match',
                  'ability': 'match',
                  'weaknesses': 'match',
                  'resistances': 'match',
                  'retreatCost': 'match',
                  'ancient_trait': 'match'}

    elif card1['supertype'] == 'Trainer':
        checks = {'name': 99,
                  'text': 'match'}

    for key, value in checks.items():
        if type(value) == int:
            if (fuzz.ratio(_get_val(card1, key),
                           _get_val(card2, key)) < value):
                return QUICKFAIL
        if value == 'match':
            if _get_val(card1, key) != _get_val(card2, key):
                return QUICKFAIL
        # count checks to see if there are the same number of entries
        if value == 'count':
            val1 = 0 if _get_val(card1, key) is None else len(
                _get_val(card1, key))
            val2 = 0 if _get_val(card2, key) is None else len(
                _get_val(card2, key))
            if val1 != val2:
                return QUICKFAIL

    return QUICKPASS


def compare_cards_full(card1, card2):
    """ Compare two pokémon cards, find ones that are close matches (perfect
    matches on field are ingored, those should be found with the --easy match)

    Return structure: {'matchlevel': [-1|0|1]}
                          -1 = not supported
                           0 = not match of checked value
                           1 = match of checked values
                       'mismatch_fields':
                            {'field':  [{
                                # which key (if multiples (e.g.attacks))
                                'index': int,
                                'score': XX,            # score on fuzzy match
                                'vals': [val1, val2]]   # versions compared
                            }],
                            'field2': ...

                       Since there can be multiple values for a field (e.g.
                       attacks), the response is returned as a list.

                       TODO - check this, currently using attack[x] to make
                       sure keys are unique.
                       Note: cardval may be a dict.
    """
    QUICKFAIL = {'matchlevel': 0}
    QUICKPASS = {'matchlevel': 1}
    NONSUPPORTED = {'matchlevel': -1}
    response = QUICKPASS

    def _build_response(field, index, score, val1, val2):
        """ Function to Build response structure when necessary

        Response Structure: response['mismatch_fields']:
            {'field':  [{
                        'index': int,      # which key (if multiples (attacks))
                        'score': XX,            # score on fuzzy match
                        'vals': [val1, val2]]   # versions compared
                      }],
            'field2': ...

        Each field is in the format of field.subfield.subfield, this references
        the particular field in the card record. For example:

        attacks.text refers "text" field of the "attacks" field, the 'index' is
            which attacks.text field specifically as there may be more than 1

        """

        # logger.debug('key={}, index={}, score={}\n\tval1=\'{}\''
        #              '\n\tval2=\'{}\''.format(key, index, score, val1, val2))
        if response.get('mismatch_fields') is None:
            response['mismatch_fields'] = {}
        if response['mismatch_fields'].get(key) is None:
            response['mismatch_fields'][key] = []
        response['mismatch_fields'][key].append({
            'index': index,
            'score': score,
            'vals': [val1, val2]
        })

    if card1['supertype'] != card2['supertype']:
        return QUICKFAIL

    # If it's not a pokemon or Trainer, continue (TODO - add more comparisons)
    if card1['supertype'] != 'Pokémon' and card1['supertype'] != 'Trainer':
        return NONSUPPORTED

    # TODO - change conditional when supporing more types, here now for
    # indent management
    if card1['supertype'] == 'Pokémon':

        # Note: checks are done in order, when an integer, any fuzzy match
        # greater than the specified value is considered a match.  Less than
        # the integer results in full rejection of the card.

        # Use different match set if Unown
        if bool(re.match('Unown', card1['name'], re.I)):
            checks = {'hp': 100,
                      'name': 90,
                      'attacks.name': 70,
                      'attacks.text': 70,
                      'text': 'match',
                      'attacks': 'count',
                      'attacks.damage': 'match',
                      'attacks.cost': 'match',
                      'attacks.convertedEnergyCost': 'match',
                      'ability.name': 'match',
                      'ability.text': 80,
                      'ability.type': 'match',
                      'weaknesses': 'match',
                      'resistances': 'match',
                      'ancient_trait': 'match',
                      'retreatCost': 'match'}
        else:
            checks = {'hp': 100,
                      'name': 80,
                      'attacks.name': 70,
                      'attacks.text': 70,
                      'text': 'match',
                      'attacks': 'count',
                      'attacks.damage': 'match',
                      'attacks.cost': 'match',
                      'attacks.convertedEnergyCost': 'match',
                      'ability.name': 'match',
                      'ability.text': 'match',
                      'ability.type': 'match',
                      'weaknesses': 'match',
                      'resistances': 'match',
                      'ancient_trait': 'match',
                      'retreatCost': 'match'}

    elif card1['supertype'] == 'Trainer':
        checks = {'name': 90,
                  'text': 'match'}
    # For each of the checks, extract a *list* of values from the cards which
    # match the check.  It's a list as there may be more than one (e.g multiple
    # attacks)
    for key, value in checks.items():
        recval1 = _get_val(card1, key)
        recval2 = _get_val(card2, key)

        # logger.debug('key = {}\nrecval1 = {}\nrecval2 = {}'.format(
        #     key, recval1, recval2))

        # if comparison value is integer, just do straight compare and if not
        # the same, then do a fuzzy compare
        if type(value) == int:
            if recval1 == recval2:
                continue

            # recval1 != recval2
            # loop through each value in the record values (e.g. attacks)
            # There may be a different number of values (e.g. again attacks)
            # loop enough times to process the longest list of the two cards
            # by padding the shorter list.  Need to loop through all so we can
            # build full list of necessary changes in the response.
            for v in range(max(len(recval1), len(recval2))):
                # if a list is exhausted, fill later loops with None
                if v == len(recval1):
                    recval1.append(None)
                if v == len(recval2):
                    recval2.append(None)

                # if they match exact, move along
                # If either of them are empty strings (""), consider them None
                if recval1[v] == "":
                    recval1[v] = None
                if recval2[v] == "":
                    recval2[v] = None

                if recval1[v] == recval2[v]:
                    continue
                # They are not exactly equal, so do a fuzzy compare and see if
                # they are significantly different (<ratio).  If they are
                # close, populate the response.
                ratio = fuzz.ratio(recval1[v], recval2[v])
                if ratio < value:
                    return QUICKFAIL
                else:
                    _build_response(key, v, ratio, recval1[v], recval2[v])

        # if comparison value is 'match' do a compare of each entry, populate
        # the response for any that are different.
        if value == 'match':
            # compensate for when one card has more values than the other by
            # adding blank entries at the end
            for v in range(max(len(recval1), len(recval2))):
                if v == len(recval1):
                    recval1.append(None)
                if v == len(recval2):
                    recval2.append(None)

                # if they match exact, move along
                # If either of them are empty strings (""), consider them None
                if recval1[v] == "":
                    recval1[v] = None
                if recval2[v] == "":
                    recval2[v] = None

                if recval1[v] == recval2[v]:
                    continue
                # if they are strings, fuzzy compare
                if type(recval1[v]) == str and type(recval2[v]) == str:
                    ratio = fuzz.ratio(recval1[v], recval2[v])
                else:
                    ratio = 0

                _build_response(key, v, ratio, recval1[v], recval2[v])

        # if comparison value is 'count' - check to see if there are exactly
        # the same number of records of that particular item.
        if value == 'count':
            count1 = 0 if recval1 is None else len(recval1)
            count2 = 0 if recval2 is None else len(recval2)
            if count1 != count2:
                _build_response(key, 0, 0, recval1, recval2)

    return response


def _get_val(record, key, level=0):
    """ return list containing value(s) for the key, handling subkeys with '.'

    recursively goes down subkeys until it receives the final record.
    if the final record is a list of dicts,  each dict in the list will
    be checked and a list of values returned.

    Examples:
    _get_val({'foo': 1}, 'foo') = [1]
    _get_val([{'foo': 1}, {'foo': 9}, {'foo': 15}], 'foo') = [1, 9, 15]
    _get_val({'foo': {'b': 7, 'bar': {'moo': 'cow'}}}, 'foo.bar.moo') = ['cow']
    _get_val({'foo': {'bar': ['duck', 'ox']}}, 'foo.bar') = [['duck', 'ox']]
    _get_val({'foo': [{'bar': 1}, {'bar': 2}]}, 'bar') = [None]
    _get_val({'foo': [{'bar': 1}, {'bar': 2}]}, 'foo')
        = [[{'bar': 1}, {'bar': 2}]]
    _get_val({'foo': [{'bar': 1}, {'ne': 1}, {'bar': 2}]}, 'foo.bar')
        = [1, None, 2]
    _get_val({'foo': [{'bar': 1}, {'ne': 1}, {'bar': 2}]}, 'foo.ne')
        = [None, 1, None]
    """
    # logger.debug('record={}\ntype={} with {} items, key={}'.format(
    #     record, type(record), len(record), key))
    keylist = key.split('.')
    if len(keylist) == 1:
        if isinstance(record, list) and isinstance(record[0], dict):
            value = []
            for item in record:
                value.append(item.get(key))
                # logger.debug('returning for key {} : {}'.format(key, value))
            return value
        # logger.debug('returning for key {} : {}'.format(
        #     key, record.get(key)))
        return [record.get(key)]
    nextrecord = {} if record.get(
        keylist[0]) is None else record.get(keylist[0])
    return _get_val(nextrecord, '.'.join(keylist[1:]), level=level + 1)


def _put_val(record, key, index, value, level=0):
    """ put a value into a record handling subkeys with '.' and list indexes

    recursively goes down subkeys until it finds the record and updates the
    value.  If the record is in a list of records, it expects an index of which
    item in the list to update.

    level is just to track the depth of recursion (not used right now)

    TODO - put examples here
    """

    keylist = key.split('.')
    # logger.debug('record type = {}'.format(type(record)))
    # logger.debug('record = {}'.format(record))
    # logger.debug('key = {}'.format(key))

    # Check to see if we're down to the final key
    if len(keylist) == 1:
        # check to see if it's a list of dictionaries
        if isinstance(record, list) and isinstance(record[0], dict):
            # logger.debug('record = {}\nkey = {}'.format(record, key))
            record[index][key] = value
            return
        # it must be a single object
        # logger.debug('record = {}\nkey = {}'.format(record, key))
        # record[key + '_was'] = record.get(key, "__missing__")
        record[key] = value
        return
    nextrecord = record.get(keylist[0])
    if nextrecord is None:
        # A parent structue is missing (e.g. abilities) - will need to created
        record[keylist[0]] = {}
        nextrecord = record.get(keylist[0])
    return _put_val(nextrecord, '.'.join(keylist[1:]), index,
                    value, level=level + 1)


def _save_error(card, key, index, newvalue):
    """ add entry to errorlist - will save to a file on exit.
    """
    oldvalue = _get_val(card, key)[index]
    errorlist.append({card['id']: {'name': card['name'],
                                   'set': card['set'],
                                   'key': key,
                                   'index': index,
                                   'newvalue': newvalue,
                                   'oldvalue': oldvalue}})


def _delete_error(card, key, index):
    """ remove entry from errorlist
    """
    for i, error in enumerate(errorlist):
        for cardid in error:
            if (cardid == card['id'] and
                key == error[cardid]['key'] and
                    index == error[cardid]['index']):
                del errorlist[i]


if __name__ == "__main__":
    main()
