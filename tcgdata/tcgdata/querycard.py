import boto3
import json
import decimal
import argparse
import logging
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr
from fuzzywuzzy import fuzz


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('--id', '-i', nargs=1, type=str,
                        required=False, help='pull specific card by id')
    # parser.add_argument('--set', '-s', nargs=1, type=str,
    #                     required=False, help='pull all cards in a set')
    parser.add_argument(
        '--standard', required=False, action="store_true",
        help='limit to only standard legal cards'
    )
    parser.add_argument(
        '--expanded', required=False, action="store_true",
        help='limit to only expanded legal cards'
    )
    parser.add_argument(
        '--ability', nargs='?', type=str, required=False,
        const=True, default=False,
        help='limit to Pokémon with abilities, next arg can be text to match',
    )
    parser.add_argument(
        '-l', '--localdb',
        action='store_true', help='use local database',
        required=False
    )
    parser.add_argument(
        '-d', '--debug',
        help="Print lots of debugging statements", action="store_const",
        dest="loglevel", const=logging.DEBUG,
        default=logging.WARNING)
    parser.add_argument(
        "-v", "--verbose",
        help="increase output verbosity", action="store_const",
        dest='loglevel', const=logging.INFO)

    args = parser.parse_args()

    # Get the service resource.
    if args.localdb:
        dynamodb = boto3.resource(
            'dynamodb', endpoint_url='http://localhost:8000')
    else:
        dynamodb = boto3.resource('dynamodb')

    cardbase_name = 'tcg_cards'
    cardtable = dynamodb.Table(cardbase_name)

    # print('Connected to table {} created at {}\n'.format(
    #     cardbase_name, cardtable.creation_date_time))

    # initialize filters
    filter = ''
    if args.standard:
        filter = filter & Attr('2018_standard').eq(True)
    if args.expanded:
        filter = filter & Attr('2018_expanded').eq(True)
    if args.ability:
        # filter = filter & Attr('ability').contains(args.ability[0])
        # filter = Attr('ability').contains(args.ability[0])
        #print('searching for {}'.format(args.ability))
        # print(args.ability)
        filter = (Attr('ability.name').contains(args.ability) |
                  Attr('ability.text').contains(args.ability))

    if args.id:
        filter = Attr('id').eq(args.id[0])
    # elif args.set:
    #     filter = Key('set_code').eq(args.set[0])
    # else:
        # filter = None
        # filter = Attr('name').contains('Mew-EX') & Attr('2017_standard').eq(True)
        # filter = filter & Attr('ability').exists()
        # filter = Attr('name').contains('Switch')
        # filter = Attr('id').eq('g1-rc15')
        # filter = Attr('abbr').contains('sum') & Attr('name').contains('Tauros-GX')
        # filter = (Attr('name').contains(
        #     '-GX') | Attr('name').contains('-EX')) & Attr('ability').exists() & Attr('2017_standard').eq(True)
        # filter = Attr('2017_expanded').eq(True) &
        # filter = Attr('subtype').contains('Basic') & Attr('evolvesFrom').not_exists() & Attr('supertype').contains('Pokémon') & Attr('retreat_cost').not_exists() & Attr('2017_expanded').eq(True)

    cards = replace_decimals(query_cards(cardtable, filter))
    print(json.dumps(cards))
    # print(json.dumps(cards))
    # print(json.dumps(cards, default=decimal_default))
    # print(len(cards))


def query_cards(cardtable, filter):
    """ Query the cardtable with the filter and return a list pokemon """
    RETRY_EXCEPTIONS = ('ProvisionedThroughputExceededException',
                        'ThrottlingException')

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
            # print('len={} response[Count]={} last_key={}'.format(
            #     len(pokemon), response['Count'], last_key))
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


def replace_decimals(obj):
    ''' return a float/int version of obj if it is a decimal

    Python's json parser can't serialize Decimal data, boto3 only returns
    numbers as decimals, so we move them into the appropriate type
    '''
    if isinstance(obj, list):
        for i in range(len(obj)):
            obj[i] = replace_decimals(obj[i])
        return obj
    elif isinstance(obj, dict):
        for k in obj:
            obj[k] = replace_decimals(obj[k])
        return obj
    elif isinstance(obj, decimal.Decimal):
        if obj % 1 == 0:
            return int(obj)
        else:
            return float(obj)
    else:
        return obj


def decimal_default(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    raise TypeError


if __name__ == "__main__":
    main()
