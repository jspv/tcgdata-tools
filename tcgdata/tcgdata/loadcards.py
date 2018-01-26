''' Load cards into the database and/or optionally post-process the data '''
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr

# For creating an outputfile of changes
from dictdiffer import diff
from pprint import pformat
from deepdiff import DeepDiff
from copy import deepcopy

import json
import argparse
import logging
import re

# Set up logging
# logger = logging.getLogger(__name__).addHandler(logging.NullHandler)
logger = logging.getLogger(__name__)
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('boto3').setLevel(logging.WARNING)

"""
    This script expects the following configuraiton files:
        * allsets.json - list of all the sets (from pullsets)
        * allcards.json - list of all the cards (from pullcards)
        * formats.json - list of seasons and sets which are valide in search
        * reprints.json - list of reprints, used to post-process the data
            already stored in the database, enriching it with reprint info
        * errata.json - errata informaiton to add to cards
"""

"""
    Notes:
        Things to track about attacks
            Status to other pkmn: sleep, paralysis, confusion, burn, poison
            Status to same pkmn: sleep, paralysis, confusion, burn, poison
            Effect to other pkmn: discard energy, can't attack, ignore damage,
            decrease damage, switch
            Effect to same pkmn: attach energy, discard energy, move energy,
            heal damage, immunity, can't attack, increase damage this turn,
            increase future damage, decrease damage, place damage counters,
            switch
            Effect to other player: no_items, no_supporter,
"""


def main():

    # Check arguments to identify databases/loadfiles
    parser = argparse.ArgumentParser(description='Arguments are optional')
    parsegroup = parser.add_mutually_exclusive_group()
    parser.add_argument(
        '-t', '--test',
        action='store_true', help='For testing - uses test data only',
        required=False
    )
    parser.add_argument(
        '-l', '--localdb',
        action='store_true', help='use local database instad of dynamodb',
        required=False
    )
    parsegroup.add_argument(
        '-kdb', '--killdb',
        action='store_true', help='delete databases if needed',
        required=False
    )
    parser.add_argument(
        '-d', '--debug',
        help="Print lots of debugging statements", action="store_const",
        dest="loglevel", const=logging.DEBUG,
        default=logging.WARNING
    )
    parser.add_argument(
        "-v", "--verbose",
        help="increase output verbosity", action="store_const",
        dest='loglevel', const=logging.INFO
    )
    parser.add_argument(
        "-u", "--updatefile", nargs=1, type=argparse.FileType('w'),
        required=False, help='File to record updates made to carddata'
    )
    parsegroup.add_argument(
        "--postprocess",
        help="Process existing table", action="store_true",
        required=False
    )
    args = parser.parse_args()

    # Get the service resource.
    if args.localdb:
        dynamodb = boto3.resource(
            'dynamodb', endpoint_url='http://localhost:8000')
    else:
        dynamodb = boto3.resource('dynamodb')

    # Set log level and configure log formatter
    logger.setLevel(args.loglevel)
    logFormatter = logging.Formatter(
        '%(asctime)s [%(filename)s] [%(funcName)s] [%(levelname)s] ' +
        '[%(lineno)d] %(message)s')

    # clear existing handlers (pythonista)
    logger.handlers = []

    # configure stream handler
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    logger.addHandler(consoleHandler)

    # Filenames, source data, configuration settings
    formats_initfile = 'formats.json'
    errata_initfile = 'errata.json'
    reprints_initfile = 'reprints.json'

    if args.updatefile:
        updatefile = args.updatefile[0]
        logger.info('Saving updates to {}'.format(updatefile.name))
    else:
        updatefile = None

    if args.test:
        cardbase_name = 'test_cards'
        cardbase_initfile = 'testcards.json'
        setbase_name = 'test_sets'
        # setbase_initfile = 'testsets.json'
        setbase_initfile = 'allsets.json'
    else:
        cardbase_name = 'tcg_cards'
        cardbase_initfile = 'allcards.json'
        setbase_name = 'tcg_sets'
        setbase_initfile = 'allsets.json'

    cardbase_KeySchema = [
        {'AttributeName': 'set_code', 'KeyType': 'HASH'},
        {'AttributeName': 'number', 'KeyType': 'RANGE'}]
    cardbase_AttributeDefinitions = [
        {'AttributeName': 'set_code', 'AttributeType': 'S'},
        {'AttributeName': 'number', 'AttributeType': 'S'}]
    cardbase_ProvisionedThroughput = {
        'ReadCapacityUnits': 1, 'WriteCapacityUnits': 1}

    setbase_KeySchema = [
        {'AttributeName': 'code', 'KeyType': 'HASH'}]
    setbase_AttributeDefinitions = [
        {'AttributeName': 'code', 'AttributeType': 'S'}]
    setbase_ProvisionedThroughput = {
        'ReadCapacityUnits': 1, 'WriteCapacityUnits': 1}

    # Get existing DynamoDB table names
    existing_tables = []
    for i_table in dynamodb.tables.all():
        existing_tables.append(i_table.table_name)
    logger.info('found existing table names {}'.format(existing_tables))

    # If database exists and wasn't told to delete first, exit.
    if not args.postprocess:
        for name in [cardbase_name, setbase_name]:
            if name in existing_tables and not args.killdb:
                logger.error(
                    '{} table already exists and was not instructed to delete'
                    ' it via --killdb'.format(name))
                quit()

    # Load the formats file which identifies the legal cards in formats
    # and load the errata_comments file
    tcgdata = {}
    tcgdata['seasons'] = {}
    tcgdata['abbreviations'] = {}
    tcgdata['sets'] = {}
    tcgdata['reprints'] = []
    with open(formats_initfile) as json_file:
        items = json.load(json_file)
        for item in items:
            if item == 'seasons' or item == 'abbreviations':
                for entry in items[item]:
                    tcgdata[item][entry] = items[item][entry]

    # Load reprints file - generated by find_reprints script
    try:
        with open(reprints_initfile) as json_file:
            reprints = json.load(json_file)
    except FileNotFoundError as e:
        print('{} does not exist, after loading tables please run'
              'findreprints and either re-import or postprocess'
              ' (TODO)'.format(reprints_initfile))
        reprints = {}

    # reprints is an array of key:[array] pairs where each key is
    # a card name.  Note: there may be multiple entries with thee
    # same card name
    for i_reprint in reprints:
        tcgdata['reprints'].append(i_reprint)

    for season in tcgdata['seasons']:
        legalsets = ''
        for set in tcgdata['seasons'][season]['standard_legal_sets']:
            logger.info("Checking set {}".format(set))
            legalsets = legalsets + tcgdata['abbreviations'][set]['abbr'] + ' '
        logger.info('Season {} Standard Format: {}'.format(season, legalsets))

    if not args.postprocess:
        # Load sets into table and into memory
        settable = create_table(dynamodb, setbase_name,
                                setbase_KeySchema,
                                setbase_AttributeDefinitions,
                                setbase_ProvisionedThroughput,
                                args.killdb, existing_tables)
        if (settable):
            tcgdata['sets'] = populate_table(settable, setbase_initfile,
                                             setbase_KeySchema,
                                             filters=[delete_nulls,
                                                      remove_oldtags],
                                             returndict=True)

        '''
        Thoughts on sets:
            release_date is in format MM/DD/YYYY - can sort these by release
                issue: promos, which may need to handle differently anyway as
                the release dates per-card affect whether they are legal or not
                for competative play.
                * May want this also to maintain order, be able to access,ouput
                sets in order.
                Idea:

                Errata - keep a json of errata.  Need to know the card/set, the
                specific attribute of the errata (text, attack, energy, etc.)
                and the updated value.
                json:
                    errata:{set, index, field, errata_update
                    TODO: what to represent in the database?

            Q: Are restored pokemon evolved?
        '''
        #  create and populate the tables.
        cardtable = create_table(dynamodb, cardbase_name,
                                 cardbase_KeySchema,
                                 cardbase_AttributeDefinitions,
                                 cardbase_ProvisionedThroughput,
                                 args.killdb, existing_tables)
        if (cardtable):
            populate_table(cardtable, cardbase_initfile, cardbase_KeySchema,
                           filters=[delete_nulls,
                                    remove_oldtags,
                                    sort_energy,
                                    x_to_times,
                                    clean_attack_text,
                                    update_card_legality,
                                    update_set_data],
                           tcgdata=tcgdata,
                           updatefile=updatefile)
    # Postprocess
    else:
        cardtable = dynamodb.Table(cardbase_name)

    # Update reprints and legality based on reprint database
    update_reprints_and_legality(
        cardtable, tcgdata['reprints'], tcgdata['seasons'])
    logger.info('Tables found: {}'.format(list(dynamodb.tables.all())))


def create_table(database, table_name, key_schema, attribute_definitions,
                 provisioned_throughput, killdb, existing_tables):
    """ Create the DynamoDB Table """
    logger.debug('In create_table, attempting to create {}'.format(table_name))
    if killdb and table_name in existing_tables:
        logger.debug(
            'Attempting to delete existing table {}'.format(table_name))

        table = database.Table(table_name)
        table.delete()
        table.meta.client.get_waiter(
            'table_not_exists').wait(TableName=table_name)
        logger.info('Table {} Deleted'.format(table_name))
    logger.info('Attempting to create table {}'.format(table_name))
    try:
        table = database.create_table(
            TableName=table_name,
            KeySchema=key_schema,
            AttributeDefinitions=attribute_definitions,
            ProvisionedThroughput=provisioned_throughput
        )
        # Wait until the table exists.
        table.meta.client.get_waiter('table_exists').wait(TableName=table_name)
    except ClientError as e:
        logger.error("Unexpected error: {}".format(e))
        return False
    logger.info('Table {} created'.format(table_name))
    return table


def populate_table(table, init_file, key_schema,
                   filters=[], returndict=False, tcgdata=False, updatefile=False):
    """ Populate the table with json specified in init_file, opt: return the data
    Position arguments:
        table -- dynamodb to populate
        init_file -- card file to load from
        key_schema -- table keys, used for debugging

    Keyword arguments:
        returndict -- boolean, return a list of populated items (default False)
        filters -- list of filter functions to run on each item.
        updatefile -- output file to record updtes

    Note: dict keys which have a value of None and string values of ''
    are removed before inserting into the table (DynamoDB requirements).
    This only should matter if there are empty strings in a list meant to hold
    a position.
    """
    logger.debug('Populating table from {}'.format(init_file))
    # In case we need to store in memory
    returnedset = {}
    with open(init_file) as json_file:
        items = json.load(json_file)
        if updatefile:
            # make backup for later diffing
            orig_items = deepcopy(items)
        itemcount = 0
        for item in items:
            logger.debug('Orig:\n{}\n'.format(item))
            for filter in filters:
                filter(item=item, tcgdata=tcgdata)
            logger.debug('After Processing:\n{}\n'.format(item))

            # If returning in-memory
            if returndict:
                # TODO - Fix this as it currenlty only works for sets
                returnedset[item['code']] = item
                # returnedset.append(item)
            try:
                table.put_item(
                    Item=item
                )
                # If debugging, pull from the database to validate_template
                if logger.getEffectiveLevel() == logging.DEBUG:
                    mykey = {}
                    for keyattribute in key_schema:
                        mykey[keyattribute['AttributeName']
                              ] = item[keyattribute['AttributeName']]
                    logger.debug('Querying table with {}'.format(mykey))
                    response = table.get_item(
                        Key=mykey
                    )
                    logger.debug(
                        'From DynamoDB:\n{}\n'.format(response['Item']))
            except ClientError as e:
                logger.error(item)
                logger.error('Error {}'.format(e))
                quit()
            print('{}\t\t{}'.format(itemcount, item['name']))
            # print('\r{}\t\t{:50}'.format(
            # itemcount, item['name']), end='', flush=True)
            itemcount = itemcount + 1

            # Break early for testing
            # if itemcount == 100:
            #     break
    print()
    if updatefile:
        logger.info('Creating updatefile...')
        for i, item in enumerate(items):
            diffresult = pformat(DeepDiff(orig_items[i], item, verbose_level=2))
            diffresult = diffresult.replace('root', item['id'])
            print(diffresult, file=updatefile)

        # diffresult = diff(orig_items, items)
        # diffresult = DeepDiff(orig_items, items)
        # pprint.pprint(diffresult, updatefile)
        # print(pprint(diffresult), file=updatefile)
        logger.info('updatefile created')
    return returnedset


def update_item(table, item):
    """ update replace the item in the table """
    try:
        table.put_item(
            Item=item
        )
    except ClientError as e:
        logger.error(item)
        logger.error('Error {}'.format(e))
        quit()


def delete_nulls(**kwargs):
    """ Recurse dict item and sub-dicts and sub-lists to remove empty values

    Required keywork arguments:
        item: item to delete nulls from
    """
    d = kwargs['item']
    if isinstance(d, dict):
        for k, v in list(d.items()):
            if isinstance(v, list) or isinstance(v, dict):
                delete_nulls(item=v)
            elif v == '' or v is None or v == 'None':
                del d[k]
    elif isinstance(d, list):
        while '' in d:
            d.remove('')
        for v in d:
            if isinstance(v, dict):
                delete_nulls(item=v)


def remove_oldtags(**kwargs):
    """ Strip any existing legality keys, we will put in our own

    Required keyword arguments:
        item - item to modify
    """
    item = kwargs['item']
    item.pop('standard_legal', None)
    item.pop('expanded_legal', None)


def update_card_legality(**kwargs):
    """ Strip any existing legal and replace with updated information.  Note:
    this does *not* handle setting legality on the reprints, it just sets the
    legality based upon the approved sets.  Reprints are marked as legal in a
    postprocess once all cards are loaded.

    Required keyword arguments
        tcg_seasons -- set structure to identify legal/non-leagal cards
        item -- item to modify
    """
    item = kwargs['item']
    tcg_seasons = kwargs['tcgdata']['seasons']

    # Check each season's legality and assign properly
    for season in tcg_seasons:

        #  Set all to false initially
        item[season + '_standard'] = False
        item[season + '_expanded'] = False
        standard_banned = expanded_banned = False

        # Check to see if the card is banned
        if item['id'] in tcg_seasons[season]['banned_standard_cards']:
            standard_banned = True
        if item['id'] in tcg_seasons[season]['banned_expanded_cards']:
            expanded_banned = True

        if (item['set_code'] in tcg_seasons[season]['standard_legal_sets'] and
                not standard_banned):
            item[season + '_standard'] = True
        if (item['set_code'] in tcg_seasons[season]['expanded_legal_sets'] and
                not expanded_banned):
            item[season + '_expanded'] = True

        # Check split sets where only cards above a certain number are
        # standard legal.  To date these are only promo series cards.
        for split_set in tcg_seasons[season]['standard_legal_split_sets']:
            if item['set_code'] == split_set['set'] and not standard_banned:
                if 'number_prefix' in split_set:
                    if item['number'].startswith(split_set['number_prefix']):
                        cardnum = int(item['number'].strip(
                            split_set['number_prefix']))
                        if cardnum >= split_set['min']:
                            item[season + '_standard'] = True
                    else:
                        # Raise an error, the expected prefix doesn't match the
                        # card information
                        raise ValueError
                else:
                    if int(item['number']) >= split_set['min']:
                        item[season + '_standard'] = True


def update_set_data(**kwargs):
    """ Insert common abbreviations and update the set names

    Required keyword arguments
        tcg_abbreviations -- key/value of database set codes and common
        abbreviations
        tcg_sets -- set data loaded from pokemon.com
    """
    item = kwargs['item']
    tcg_abbreviations = kwargs['tcgdata']['abbreviations']
    tcg_sets = kwargs['tcgdata']['sets']

    # Add set data
    item['set_total_cards'] = tcg_sets[item['set_code']]['total_cards']
    item['set_release_date'] = tcg_sets[item['set_code']]['release_date']

    if item['set_code'] in tcg_abbreviations:
        setcode = item['set_code']
        item['abbr'] = tcg_abbreviations[setcode]['abbr']
        item['set'] = tcg_abbreviations[setcode]['name']


def update_reprints_and_legality(table, tcg_reprints, tcg_seasons):
    """ Loop throgh cards and add list of reprints """

    # Check to see if the name matches and the card is listed
    #  -- Note also checking to see if the card is listed under any reprint
    # and will raise an error if name doesn't match.  Error Checking

    logger.info('Updating reprints data')
    # Cards in tcg_repritns are in a cardname:[list...] structure
    for card in tcg_reprints:
        [(cardname, cardprint_ids)] = card.items()

        # list to hold records of each card in cardprint_ids, this will be
        # used later to update the records before writing them back to the db
        cardprint_data = []

        # Check to see each card in the reprint list exists in the database
        # if found, add the reprint list to the card record
        for cardprint_id in cardprint_ids:
            [cardset, cardnumber] = cardprint_id.split('-')
            # For some sets, card number contains alpha characters, these
            # are always uppercase, card ids are not. e.g. g1-rc15 vs. g1 RC15
            response = table.query(
                KeyConditionExpression=Key('set_code').eq(cardset) &
                Key('number').eq(cardnumber.upper())
            )

            # check the response from the database
            item = response['Items']
            if len(item) != 1:
                print('Error finding card {} ({}), recieved {} cards after'
                      'query'.format(cardprint_id, cardname, len(item)))
            else:
                cardprint_data.append(item[0])

        # loop throug the loaded card records and set the 'reprints' value, at
        # the same time, verify the names match for error checking
        #
        # Also: check for each season, if *any* of the cards are marked legal
        # for a season, set the legal flag and take a second pass through
        # marking all reprint cards as legal for that season and update the
        # database.

        # list of formats identified as legal for the card
        legalformats = []

        # search through reprints, set reprints attribute and also check
        # if any of them are legal in each format
        for cardprint in cardprint_data:
            if cardprint['name'] == cardname:
                cardprint['reprints'] = cardprint_ids
                for season in tcg_seasons:
                    if cardprint[season + '_standard'] is True:
                        legalformats.append(season + '_standard')
                    if cardprint[season + '_expanded'] is True:
                        legalformats.append(season + '_expanded')
            else:
                print('Error found match on card {} with id {} with '
                      'reprints name {}'.format(cardprint['name'],
                                                cardprint['id'], cardname))
                raise ValueError

        # For each legal format - update the legality of all reprints and
        # update and the database
        for cardprint in cardprint_data:
            for season_format in legalformats:
                cardprint[season_format] = True
            try:
                table.put_item(
                    Item=cardprint
                )
            except ClientError as e:
                logger.error(cardprint)
                logger.error('Error {}'.format(e))
                quit()


def sort_energy(**kwargs):
    """ Ensure energy costs are sorted - allows for better matching """
    item = kwargs['item']
    if item.get('attacks'):
        for attack in item['attacks']:
            if attack.get('cost'):
                attack['cost'].sort()
                if attack['cost'] != ['Free']:
                    attack['convertedEnergyCost'] = len(attack['cost'])
                else:
                    attack['convertedEnergyCost'] = 0
            else:
                attack['cost'] = ['Free']
                attack['convertedEnergyCost'] = 0


def x_to_times(**kwargs):
    """ Change where the letter x was used when it should have been \xd7

    Patterns:

    Change x to 'times' when letter x is used in x+d (e.g. x2) or d+ (e.g. 20x)
            (r'\b(\d+)x\b', r'\1×'),
            (r'\bx(\d+)\b', r'×\1')

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
                        d[k] = re.sub(pattern, replacement, v)
                        logger.debug('replaced [{}]'.format(d[k]))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            if isinstance(v, str):
                for pattern, replacement in patterns:
                    if re.search(pattern, v):
                        logger.debug('replacing[{}]'.format(d[i]))
                        d[i] = re.sub(pattern, replacement, v)
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


if __name__ == "__main__":
    main()
