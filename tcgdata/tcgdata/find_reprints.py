''' Search through database and detect reprints '''
import builtins
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


def main():
    # webtest()
    # builtins.wait("waiting")
    parser = argparse.ArgumentParser()
    parser.add_argument('--easy', '-e', action='store_true',
                        help='find easy matches only', required=False)
    parser.add_argument('--file', '-f', nargs=1, type=argparse.FileType('w'),
                        default=[sys.stdout], required=False,
                        help='output to file',)
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
    parser.add_argument('-t', '--test', action='store_true',
                        help='Dev testing', required=False)

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

    # Place to dump quick tests
    if args.test:
        card1 = pickle.loads(b'\x80\x03}q\x00(X\x0c\x00\x00\x00retreat_costq\x01]q\x02(X\t\x00\x00\x00Colorlessq\x03X\t\x00\x00\x00Colorlessq\x04X\t\x00\x00\x00Colorlessq\x05eX\x05\x00\x00\x00typesq\x06]q\x07X\t\x00\x00\x00Lightningq\x08aX\t\x00\x00\x00supertypeq\tX\x08\x00\x00\x00Pok\xc3\xa9monq\nX\x03\x00\x00\x00setq\x0bX\x0e\x00\x00\x00Secret Wondersq\x0cX\x0f\x00\x00\x00set_total_cardsq\rcdecimal\nDecimal\nq\x0eX\x03\x00\x00\x00132q\x0f\x85q\x10Rq\x11X\x06\x00\x00\x00artistq\x12X\x0c\x00\x00\x00Kouki Saitouq\x13X\t\x00\x00\x00image_urlq\x14X&\x00\x00\x00https://images.pokemontcg.io/dp3/1.pngq\x15X\x02\x00\x00\x00hpq\x16X\x03\x00\x00\x00130q\x17X\x0b\x00\x00\x00resistancesq\x18]q\x19}q\x1a(X\x04\x00\x00\x00typeq\x1bX\x05\x00\x00\x00Metalq\x1cX\x05\x00\x00\x00valueq\x1dX\x03\x00\x00\x00-20q\x1euaX\x10\x00\x00\x00set_release_dateq\x1fX\n\x00\x00\x0011/01/2007q X\x10\x00\x00\x00image_url_hi_resq!X,\x00\x00\x00https://images.pokemontcg.io/dp3/1_hires.pngq"X\r\x00\x00\x002017_standardq#\x89X\r\x00\x00\x002017_expandedq$\x89X\x17\x00\x00\x00national_pokedex_numberq%h\x0eX\x03\x00\x00\x00181q&\x85q\'Rq(X\x06\x00\x00\x00numberq)X\x01\x00\x00\x001q*X\x08\x00\x00\x00set_codeq+X\x03\x00\x00\x00dp3q,X\x07\x00\x00\x00subtypeq-X\x07\x00\x00\x00Stage 2q.X\x07\x00\x00\x00attacksq/]q0}q1(X\x04\x00\x00\x00nameq2X\x0c\x00\x00\x00Cluster Boltq3X\x06\x00\x00\x00damageq4X\x02\x00\x00\x0070q5X\x04\x00\x00\x00costq6]q7(X\t\x00\x00\x00Colorlessq8X\t\x00\x00\x00Colorlessq9X\t\x00\x00\x00Lightningq:eX\x04\x00\x00\x00textq;X\xf2\x00\x00\x00You may discard all Lightning Energy attached to Ampharos. If you do, this attack does 20 damage to each of your opponent\'s Benched Pok\xc3\xa9mon that has any Energy cards attached to it. (Don\'t apply Weakness and Resistance for Benched Pok\xc3\xa9mon.)q<X\x13\x00\x00\x00convertedEnergyCostq=h\x0eX\x01\x00\x00\x003q>\x85q?Rq@uaX\x06\x00\x00\x00seriesqAX\x0f\x00\x00\x00Diamond & PearlqBX\n\x00\x00\x00weaknessesqC]qD}qE(h\x1bX\x08\x00\x00\x00FightingqFh\x1dX\x03\x00\x00\x00+30qGuah2X\x08\x00\x00\x00AmpharosqHX\x02\x00\x00\x00idqIX\x05\x00\x00\x00dp3-1qJX\x07\x00\x00\x00abilityqK}qL(h2X\x07\x00\x00\x00JammingqMh\x1bX\n\x00\x00\x00Pok\xc3\xa9-BodyqNh;X\xb2\x00\x00\x00After your opponent plays a Supporter card from his or her hand, put 1 damage counter on each of your opponent\'s Pok\xc3\xa9mon. You can\'t use more than 1 Jamming Pok\xc3\xa9-Body each turn.qOuX\x06\x00\x00\x00rarityqPX\t\x00\x00\x00Rare HoloqQu.')

        card2 = pickle.loads(b'\x80\x03}q\x00(X\x0c\x00\x00\x00retreat_costq\x01]q\x02(X\t\x00\x00\x00Colorlessq\x03X\t\x00\x00\x00Colorlessq\x04X\t\x00\x00\x00Colorlessq\x05eX\x05\x00\x00\x00typesq\x06]q\x07X\t\x00\x00\x00Lightningq\x08aX\t\x00\x00\x00supertypeq\tX\x08\x00\x00\x00Pok\xc3\xa9monq\nX\x03\x00\x00\x00setq\x0bX\x0c\x00\x00\x00POP Series 7q\x0cX\x0f\x00\x00\x00set_total_cardsq\rcdecimal\nDecimal\nq\x0eX\x02\x00\x00\x0017q\x0f\x85q\x10Rq\x11X\x06\x00\x00\x00artistq\x12X\x0c\x00\x00\x00Kouki Saitouq\x13X\t\x00\x00\x00image_urlq\x14X\'\x00\x00\x00https://images.pokemontcg.io/pop7/1.pngq\x15X\x02\x00\x00\x00hpq\x16X\x03\x00\x00\x00130q\x17X\x0b\x00\x00\x00resistancesq\x18]q\x19}q\x1a(X\x04\x00\x00\x00typeq\x1bX\x05\x00\x00\x00Metalq\x1cX\x05\x00\x00\x00valueq\x1dX\x03\x00\x00\x00-20q\x1euaX\x10\x00\x00\x00set_release_dateq\x1fX\n\x00\x00\x0003/01/2008q X\x10\x00\x00\x00image_url_hi_resq!X-\x00\x00\x00https://images.pokemontcg.io/pop7/1_hires.pngq"X\r\x00\x00\x002017_standardq#\x89X\r\x00\x00\x002017_expandedq$\x89X\x17\x00\x00\x00national_pokedex_numberq%h\x0eX\x03\x00\x00\x00181q&\x85q\'Rq(X\x06\x00\x00\x00numberq)X\x01\x00\x00\x001q*X\x08\x00\x00\x00set_codeq+X\x04\x00\x00\x00pop7q,X\x07\x00\x00\x00subtypeq-X\x07\x00\x00\x00Stage 2q.X\x07\x00\x00\x00attacksq/]q0}q1(X\x04\x00\x00\x00nameq2X\x0c\x00\x00\x00Cluster Boltq3X\x06\x00\x00\x00damageq4X\x02\x00\x00\x0070q5X\x04\x00\x00\x00costq6]q7(X\t\x00\x00\x00Colorlessq8X\t\x00\x00\x00Colorlessq9X\t\x00\x00\x00Lightningq:eX\x04\x00\x00\x00textq;X\xe8\x00\x00\x00You may discard all Energy attached to Ampharos. If you do, this attack does 20 damage to each of your opponent\'s Benched Pok\xc3\xa9mon that has any Energy cards attached to it. (Don\'t apply Weakness and Resistance for Benched Pok\xc3\xa9mon.)q<X\x13\x00\x00\x00convertedEnergyCostq=h\x0eX\x01\x00\x00\x003q>\x85q?Rq@uaX\x06\x00\x00\x00seriesqAX\x03\x00\x00\x00POPqBX\n\x00\x00\x00weaknessesqC]qD}qE(h\x1bX\x08\x00\x00\x00FightingqFh\x1dX\x03\x00\x00\x00\xc3\x972qGuah2X\x08\x00\x00\x00AmpharosqHX\x02\x00\x00\x00idqIX\x06\x00\x00\x00pop7-1qJX\x07\x00\x00\x00abilityqK}qL(h2X\x07\x00\x00\x00JammingqMh\x1bX\n\x00\x00\x00Pok\xc3\xa9-BodyqNh;X\xb2\x00\x00\x00After your opponent plays a Supporter card from his or her hand, put 1 damage counter on each of your opponent\'s Pok\xc3\xa9mon. You can\'t use more than 1 Jamming Pok\xc3\xa9-Body each turn.qOuX\x06\x00\x00\x00rarityqPX\x04\x00\x00\x00RareqQu.')

        matchdata = pickle.loads(
            b"\x80\x03}q\x00(X\x0f\x00\x00\x00attacks.text[0]q\x01]q\x02}q\x03(X\x05\x00\x00\x00scoreq\x04KbX\x04\x00\x00\x00valsq\x05]q\x06(X\xf2\x00\x00\x00You may discard all Lightning Energy attached to Ampharos. If you do, this attack does 20 damage to each of your opponent's Benched Pok\xc3\xa9mon that has any Energy cards attached to it. (Don't apply Weakness and Resistance for Benched Pok\xc3\xa9mon.)q\x07X\xe8\x00\x00\x00You may discard all Energy attached to Ampharos. If you do, this attack does 20 damage to each of your opponent's Benched Pok\xc3\xa9mon that has any Energy cards attached to it. (Don't apply Weakness and Resistance for Benched Pok\xc3\xa9mon.)q\x08euaX\r\x00\x00\x00weaknesses[0]q\t]q\n}q\x0b(h\x04K\x00h\x05]q\x0c(]q\r}q\x0e(X\x04\x00\x00\x00typeq\x0fX\x08\x00\x00\x00Fightingq\x10X\x05\x00\x00\x00valueq\x11X\x03\x00\x00\x00+30q\x12ua]q\x13}q\x14(X\x04\x00\x00\x00typeq\x15X\x08\x00\x00\x00Fightingq\x16X\x05\x00\x00\x00valueq\x17X\x03\x00\x00\x00\xc3\x972q\x18uaeuau.")

        logger.info(review_cards_manually(card1, card2, matchdata))
        logger.info('done with test')
        quit()

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

    cardfilter = None
    cards = query_cards(cardtable, cardfilter)
    print(find_reprints(cards, is_easymode), file=args.file[0])


def find_reprints(cards, is_easymode):
    """ Search through a list of card objects and find all reprints """

    # holder for list of reprints in the format of {Name:[cardid, cardid]}
    reprintslist = []

    # Use an index i so that we can pass the current index to the
    # fund_reprints_x function indicating where to start the search from.
    # cards prior to i would have been checked already.
    for i, card in enumerate(cards):
        supertype = card['supertype']

        if supertype == 'Pokémon':

            # if there are any reprint objects in the reprintslist, check to
            # see if the current card is already listed in any of them, if not
            # then go ahead and search for reprints.
            if not any(card['id'] in prints.get(card['name'], {})
                       for prints in reprintslist):
                print(i)
                reprints = find_reprints_pokemon(cards, i, is_easymode)
                if reprints:
                    reprintslist.append(reprints)
                    # with open('manual_reprints.json', 'a') as outfile:
                    # print(json.dumps(reprintslist),
                    #       file=outfile)
                    print(json.dumps(reprints))

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

    # It's a detailed/fuzzy search
    for k in range(index + 1, len(cards)):
        card2 = cards[k]
        try:
            response = compare_cards_full(card1, card2)
        # catch all exeptions, print cards and reraise
        except Exception as e:
            print('\n\ncard1=\n{}\n\ncard2=\n{}\n\n'.format(card1, card2))
            raise

        if (response['matchlevel'] == 1 and
                response.get('mismatch_fields') is not None):
            logger.info('{!a}'.format(response))
            # print(pickle.dumps(card1), '\n\n', pickle.dumps(card2),
            #       '\n\n',  pickle.dumps(response['mismatch_fields']))

            # Cards need manual review
            reviewstatus = review_cards_manually(
                card1, card2, response['mismatch_fields'])
            if reviewstatus['matched'] is True:

                # Write the errors to the error file and apply them to the
                # cards in memory.  Errors is a list of 2 key/value dicts
                for error in reviewstatus['errors']:
                    print(error['id'])
                    print(error['field'])
                    print(error['newvalue'])
                    _put_val(cards[error['id']],
                             cards[error['field']],
                             cards[error['newvalue']])

                    # card[id][field + '_was'] = card[id][field]

        # # TODO - get logic here
        # if response:
        #     pass

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

    Return structure: {matchlevel: [-1|0|1]}
                          -1 = not supported
                           0 = not match of checked value
                           1 = match of checked values
                       mismatch_fields: {field: [{score: fuzzyscore,
                                                   vals:[card1val, cardval]}]

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

    # Build response structure
    def _key_response(key, score, val1, val2):
        logger.debug('key={}, score={}\n\tval1=\'{}\'\n\tval2=\'{}\''.format(
            key, score, val1, val2
        ))
        if response.get('mismatch_fields') is None:
            response['mismatch_fields'] = {}
        if response['mismatch_fields'].get(key) is None:
            response['mismatch_fields'][key] = []
        response['mismatch_fields'][key].append({
            'score': score,
            'vals': [val1, val2]
        })

    # If it's not a pokemon, continue (TODO - add more comparisons)
    if card1['supertype'] != card2['supertype']:
        return QUICKFAIL
    if card1['supertype'] != 'Pokémon':
        return NONSUPPORTED

    # TODO - change conditional when supporing more types, here now for
    # indent management
    if card1['supertype'] == 'Pokémon':

        # Note: checks are done in order, when an integer, any fuzzy match
        # greater than the specified value is considered a match.  Less than
        # the integer results in full rejection of the card.
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
                  'ability.text': 'match',
                  'ability.type': 'match',
                  'weaknesses': 'match',
                  'resistances': 'match',
                  'ancient_trait': 'match',
                  'retreat_cost': 'match'}

    for key, value in checks.items():
        recval1 = _get_val(card1, key)
        recval2 = _get_val(card2, key)

        if type(value) == int:
            if recval1 == recval2:
                continue
            # loop through each value in the record values (e.g. attacks)
            # loop enough times to process the longest list of the two cards
            for v in range(max(len(recval1), len(recval2))):
                # if a list is exhausted, fill later loops with ""
                if v == len(recval1):
                    recval1.append("")
                if v == len(recval2):
                    recval2.append("")
                if recval1[v] == recval2[v]:
                    continue
                ratio = fuzz.ratio(recval1[v], recval2[v])
                if ratio < value:
                    return QUICKFAIL
                else:
                    _key_response(key + '[' + str(v) + ']',
                                  ratio, recval1[v], recval2[v])
        if value == 'match':
            # compensate for when one card has more values than the other by
            # adding blank entries at the end
            for v in range(max(len(recval1), len(recval2))):
                if v == len(recval1):
                    recval1.append("")
                if v == len(recval2):
                    recval2.append("")
                # if they match, move along
                if recval1[v] == recval2[v]:
                    continue
                if type(recval1[v]) == str and type(recval2[v]) == str:
                    ratio = fuzz.ratio(recval1[v], recval2[v])
                else:
                    ratio = 0
                _key_response(key + '[' + str(v) + ']',
                              ratio, recval1[v], recval2[v])
        if value == 'count':
            count1 = 0 if recval1 is None else len(recval1)
            count2 = 0 if recval2 is None else len(recval2)
            if count1 != count2:
                _key_response(key, 0, recval1, recval2)

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


def _put_val(record, key, value):
    """ put a value into a record handling subkeys with '.' and list indexes

    recursively goes down subkeys until it finds the record and updates the
    value.  If the record is in a list of records, it expects an index of which
    item in the list to update.

    TODO - put examples here
    """

    keylist = key.split('.')
    if len(keylist) == 1:
        if isinstance(record, list) and isinstance(record[0], dict):
            # There should be an index embedded in the key [x] if not - error
            index = int(keylist[keylist.find('[' + 1):keylist.find(']')])
            logger.debug('index is ' + index)
            key = keylist[:keylist.find('[')]
            logger.debug('key is ' + key)
            record[index][key + '_was'] = record[index][key]
            record[index][key] = value
            return
        record[key + '_was'] = record[key]
        record[key] = value
        return
    nextrecord = record.get(keylist[0])
    return _put_val(nextrecord, '.'.join(kelist[1:]))


if __name__ == "__main__":
    main()
