import logging
import re

# Initialise the logger
logger = logging.getLogger(__name__)


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
    Remove when attack damage is included in the attack text e.g. "(20+) This
        attack does 20 damage plus ..."

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


def add_converted_reteat_cost(**kwargs):
    ''' Calculate convertedRetreatCost and add to the card structure '''

    card = kwargs['card']
    if card.get('retreatCost'):
        card['convertedRetreatCost'] = len(card['retreatCost'])
