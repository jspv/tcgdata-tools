''' Search through database and detect reprints '''
import builtins
import os
import boto3
import json
import argparse
import sys
import logging
import pickle
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr
from fuzzywuzzy import fuzz
from tcgdata.forms import Form, create_compare_form
from tcgdata.forms import display_cards, review_cards_manually

logger = logging.getLogger(__name__)
# trootlogger=logging.getLogger()
# print(trootlogger)
# trootlogger.setLevel(logging.DEBUG)

# logger = logging.getLogger()
# logging.getLogger('botocore').setLevel(logging.WARNING)
# logging.getLogger('boto3').setLevel(logging.WARNING)

# Nasty Global
errorlist = []


def main():
    # ensure we use the global errorlist
    global errorlist
    # webtest()
    # builtins.wait("waiting")
    parser = argparse.ArgumentParser()
    parser.add_argument('--easy', '-e', action='store_true',
                        help='find easy matches only', required=False)
    parser.add_argument('--reprintsfile', '-rf', nargs=1,
                        type=argparse.FileType('w'),
                        default=[sys.stdout], required=False,
                        help='load then output reprints to file')
    parser.add_argument('--errorfile', '-ef', nargs=1,
                        help='load then output errors to file')
    parser.add_argument('--hard', action='store_true',
                        help='find hard matches', required=False)
    parser.add_argument('-l', '--localdb', action='store_true',
                        help='use local database', required=False)
    parser.add_argument('-d', '--debug', action="store_const",
                        help="Set debug for local functions",
                        dest="loglevel", const=logging.DEBUG,
                        default=logging.WARNING)
    parser.add_argument("-v", "--verbose", action="store_const",
                        help="increase output verbosity for local functions",
                        dest='loglevel', const=logging.INFO)
    parser.add_argument('-dd', '--deepdebug', action="store_const",
                        help="Print lots of debugging statements",
                        dest="deeploglevel", const=logging.DEBUG,
                        default=logging.WARNING)
    parser.add_argument("-vv", "--deepverbose", action="store_const",
                        help="increase output verbosity",
                        dest='deeploglevel', const=logging.INFO)

    args = parser.parse_args()

    # Set log level and configure log formatter of the *root* logger
    rootlogger = logging.getLogger()
    logFormatter = logging.Formatter(
        '%(asctime)s [%(filename)s] [%(funcName)s] [%(levelname)s] ' +
        '[%(lineno)d] %(message)s')
    # clear existing handlers (pythonista)
    rootlogger.handlers = []

    # configure stream handler and add it to the root logger
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    rootlogger.addHandler(consoleHandler)
    rootlogger.setLevel(args.deeploglevel)

    # configure local package logging.  This file's logger (__name__) will be
    # in the format of package.name, the root logger controls all logging, so
    # if just want the local package, we can grab the first token in
    # package.name
    if args.deeploglevel != args.loglevel:
        logging.getLogger(__name__.split('.')[0]).setLevel(args.loglevel)

    if args.hard and args.easy:
        parser.error("--easy and --hard are mutually exclusive")
        sys.exit(2)
    if not (args.hard or args.easy):
        parser.error("--easy or --hard required")
        sys.exit(2)

    is_easymode = True if args.easy else False

    # Get the service resource.
    if args.localdb:
        dynamodb = boto3.resource(
            'dynamodb', endpoint_url='http://localhost:8000')
    else:
        dynamodb = boto3.resource('dynamodb')

    cardbase_name = 'tcg_cards'
    cardtable = dynamodb.Table(cardbase_name)

    print('Connected to table {} created at {}\n'.format(
        cardbase_name, cardtable.creation_date_time))

    # if cardfilter = None, get all cards
    cardfilter = None
    cards = query_cards(cardtable, cardfilter)

    # initialise errorlist - if the file exists, load the json files
    if args.errorfile and os.path.isfile(args.errorfile[0]):
        with open(args.errorfile[0], 'r') as errorfile:
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
                    _put_val(card, errorstruct['key'], errorstruct['index'],
                             errorstruct['newvalue'])
    else:
        errorlist = []

    print(find_reprints(cards, is_easymode), file=args.reprintsfile[0])

    if args.errorfile:
        with open(args.errorfile[0], 'w') as errorfile:
            logger.debug('errorlist = {}'.format(errorlist))
            print(json.dumps(errorlist), file=errorfile)


def find_reprints(cards, is_easymode):
    """ Search through a list of card objects and find all reprints """

    # holder for list of reprints in the format of:
    #   [{Name:[cardid, cardid]}, {Name:[cardid, cardid, cardid]}]
    reprintslist = []

    # Use an index i so that we can pass the current index to the
    # find_reprints_x function indicating where to start the search from.
    # cards prior to i would have been checked already.
    for i, card in enumerate(cards):
        supertype = card['supertype']

        if supertype == 'Pokémon':

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
                print(i)
                try:
                    reprints = find_reprints_pokemon(cards, i, is_easymode)
                    if reprints:
                        reprintslist.append(reprints)
                        # with open('manual_reprints.json', 'a') as outfile:
                        # print(json.dumps(reprintslist),
                        #       file=outfile)
                        print(json.dumps(reprints))
                except Exception as e:
                    print('Quit chosen or something else happened.  Exiting')
                    print('Exception was {}'.format(e))
                    print('Errorlist is {}'.format(errorlist))
                    return(json.dumps(reprintslist))

    return(json.dumps(reprintslist))


def find_reprints_pokemon(cards, index, find_easy=False):
    """ identify reprints, return reprintslist """

    reprintslist = {}
    card1 = cards[index]
    if find_easy:
        # check each card starting from the next card in the index, it is
        # presumed that the earlier cards have already been checked.
        for k in range(index + 1, len(cards)):
            card2 = cards[k]
            if compare_cards_easy(card1, card2)['matchlevel'] == 1:
                if len(reprintslist) == 0:
                    reprintslist[card1['name']] = [card1['id']]
                reprintslist[card1['name']].append(card2['id'])

        if reprintslist:
            return(reprintslist)
        return None

    # It's a detailed/fuzzy search (hard)
    for k in range(index + 1, len(cards)):
        card2 = cards[k]
        try:
            response = compare_cards_full(card1, card2)
        # catch all exeptions, print cards and reraise
        except Exception as e:
            print('\n\ncard1=\n{}\n\ncard2=\n{}\n\n'.format(card1, card2))
            raise

        # matchlevel of 1 means possible match
        if (response['matchlevel'] == 1 and
                response.get('mismatch_fields') is not None):
            logger.info('{!a}'.format(response))
            # print(pickle.dumps(card1), '\n\n', pickle.dumps(card2),
            #       '\n\n',  pickle.dumps(response['mismatch_fields']))

            # Send the cards off for manual review of the picture
            # return struct = {
            # 'matched' : True, False 'Quit' or 'Error'
            # 'review': [id, id]
            # 'errors': [{'id': cardid,
            #             'field': field_to_fix,
            #             'index': index_in_field,
            #             'newvalue': new_text},]}
            reviewstatus = review_cards_manually(
                card1, card2, response['mismatch_fields'])

            logger.debug(
                'Return from review_cards_manually = {}'.format(reviewstatus))
            # if one of the cards matched the picture, mark the cards as
            # matched, fix the error, and update the reprintslist
            if reviewstatus['matched'] == 'True':
                # Write the errors to the error file and apply them to the
                # cards in memory.  Errors is a list of 2 key/value dicts
                for error in reviewstatus['errors']:
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
            elif reviewstatus['matched'] == 'False':
                response['matchlevel'] = 0

            # Abort early if quit was chosen
            elif reviewstatus['matched'] == 'Quit':
                raise Exception('Quit Exception')

            # Should never get here, abort
            else:
                raise Exception('Bad Reviewstatus')

        # if matched, add to reprints list
        if (response['matchlevel'] == 1):
            if len(reprintslist) == 0:
                reprintslist[card1['name']] = [card1['id']]
            reprintslist[card1['name']].append(card2['id'])

            return(reprintslist)

        # # TODO - get logic here
        # if response:
        #     pass
    if reprintslist:
        return reprintslist


def query_cards(cardtable, filter):
    """ Query the cardtable with the filter and return a list pokemon """

    # We cannot begin with ExclusiveStartKey=None, so we use kwargs sans that
    # the first time, then update to include it subsequently.
    scan_kw = {}
    if filter:
        scan_kw.update({'FilterExpression': filter})
    retries = 0
    pokemon = []
    while True:
        try:
            response = cardtable.scan(**scan_kw)
            pokemon.extend(response['Items'])
            last_key = response.get('LastEvaluatedKey')
            print('len={} response[Count]={} last_key={}'.format(
                len(pokemon), response['Count'], last_key))
            if not last_key:
                break
            retries = 0          # if successful, reset count
            scan_kw.update({'ExclusiveStartKey': last_key})
        except ClientError as err:
            if err.response['Error']['Code'] not in RETRY_EXCEPTIONS:
                raise
            print('WHOA, too fast, slow it down retries={}'.format(retries))
            sleep(2 ** retries)
            retries += 1     # TODO max limit
    return pokemon


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

    if card1['supertype'] != 'Pokémon':
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
                  'retreat_cost': 'match',
                  'ancient_trait': 'match'}

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

        logger.debug('key={}, index={}, score={}\n\tval1=\'{}\''
                     '\n\tval2=\'{}\''.format(key, index, score, val1, val2))
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

    # If it's not a pokemon, continue (TODO - add more comparisons)
    if card1['supertype'] != 'Pokémon':
        return NONSUPPORTED

    # TODO - change conditional when supporing more types, here now for
    # indent management
    if card1['supertype'] == 'Pokémon':

        # Note: checks are done in order, when an integer, any fuzzy match
        # greater than the specified value is considered a match.  Less than
        # the integer results in full rejection of the card.
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
                  'retreat_cost': 'match'}

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
            # TODO - Need to remember why I'm doing the padding of different
            # sized lists - seems if they are different size it's never a match
            for v in range(max(len(recval1), len(recval2))):
                # if a list is exhausted, fill later loops with ""
                if v == len(recval1):
                    recval1.append("")
                if v == len(recval2):
                    recval2.append("")
                if recval1[v] == recval2[v]:
                    continue
                # They are not exactly equal, so do a fuzzy compare and see if
                # they are significantly different (<ratio).  If they are
                # close, populate the response.
                ratio = fuzz.ratio(recval1[v], recval2[v])
                if ratio < value:
                    return QUICKFAIL
                else:
                    if (recval1[v] == "" or recval2[v] == ""):
                        print(
                            '\n\n\n*************\n***  TODO MET  ***\n*************\n\n\n')
                    _build_response(key, v, ratio, recval1[v], recval2[v])

        # if comparison value is 'match' do a compare of each entry, populate
        # the response for any that are different.
        if value == 'match':
            # compensate for when one card has more values than the other by
            # adding blank entries at the end
            for v in range(max(len(recval1), len(recval2))):
                if v == len(recval1):
                    recval1.append("")
                if v == len(recval2):
                    recval2.append("")
                # if they match exact, move along
                if recval1[v] == recval2[v]:
                    continue
                if type(recval1[v]) == str and type(recval2[v]) == str:
                    ratio = fuzz.ratio(recval1[v], recval2[v])
                else:
                    ratio = 0
                if (recval1[v] == "" or recval2[v] == ""):
                    print(
                        '\n\n\n*************\n***  TODO MET  ***\n*************\n\n\n')
                _build_response(key, v, ratio, recval1[v], recval2[v])

        # if comparison value is 'count' - check to see if there are exactly
        # the same number of records of that particular item.
        if value == 'count':
            count1 = 0 if recval1 is None else len(recval1)
            count2 = 0 if recval2 is None else len(recval2)
            if count1 != count2:
                _build_response(key, 0, 0, recval1, recval2)

    return response


def _get_val(record, key):
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
    return _get_val(nextrecord, '.'.join(keylist[1:]))


def _put_val(record, key, index, value, level=0):
    """ put a value into a record handling subkeys with '.' and list indexes

    recursively goes down subkeys until it finds the record and updates the
    value.  If the record is in a list of records, it expects an index of which
    item in the list to update.

    level is just to track the depth of recursion (not used right now)

    TODO - put examples here
    """

    keylist = key.split('.')

    # Check to see if we're down to the final key
    if len(keylist) == 1:
        # check to see if it's a list of dictionaries
        if isinstance(record, list) and isinstance(record[0], dict):
            logger.debug('record = {}\nkey = {}'.format(record, key))
            record[index][key + '_was'] = record[index].get(key, "__missing__")
            record[index][key] = value
            return
        # it must be a single object
        # logger.debug('record = {}\nkey = {}'.format(record, key))
        record[key + '_was'] = record.get(key, "__missing__")
        record[key] = value
        return
    nextrecord = record.get(keylist[0])
    return _put_val(nextrecord, '.'.join(keylist[1:]), index,
                    value, level=level + 1)


def _save_error(card, key, index, newvalue):
    """ add entry to errorlist - will save to a file on exit.
    """
    oldvalue = _get_val(card, key)[index]
    errorlist.append({card['id']: {'key': key,
                                   'index': index,
                                   'newvalue': newvalue,
                                   'oldvalue': oldvalue}})
    logger.debug(errorlist)


if __name__ == "__main__":
    main()
