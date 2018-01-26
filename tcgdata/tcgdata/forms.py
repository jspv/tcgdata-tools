from wtforms.fields import *
from wtforms import widgets
from wtforms.validators import DataRequired
# from wtforms.fields.html5 import EmailField
from flask import Flask, render_template, request, flash
from flask_wtf import FlaskForm
import webbrowser
import logging
# import logging_tree

logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


class Form(FlaskForm):
    """ Make FlaskForm my default Form """
    pass


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


def create_compare_form(*args, **kwargs):

    # First we create the base form
    # Note that we are not adding any fields to it yet

    class CompareForm(Form):
        no_match = SubmitField(label='Not a Match')
        process_changes = SubmitField(label='Fix Match')
        quit = SubmitField(label='Quit')

        flag_for_edits = MultiCheckboxField(
            'Flag for later Review',
            choices=[('flag_left', 'Review Later'),
                     ('flag_right', 'Review Later')]
        )

    # the matchrecord dictionary contains a list of the fields
    # that differed between the cards
    # {field: [{'score': fuzzyscore,
    #           'vals':[card1val, cardval],
    #           'index': int}]
    for key, value in kwargs['matchrecord'].items():
        # Need to break items up into tuples of name, value.  Choosing to
        # name them select0, select1, etc.
        # print('value is {}'.format(value))
        choices = []
        # grab each card's entry and create a selection radio box
        for num, item in enumerate(value[0]['vals']):
            if item is None:
                item = "__None__"
            choices.append(('select_' + str(num), item))
        setattr(CompareForm, key, RadioField(choices=choices))
    return CompareForm(**kwargs)


def display_cards(card0, card1):

    # Get images
    image0 = card0.get('image_url_hi_res')
    image0 = image0.replace(
        'https://images.pokemontcg.io/',
        'images/')
    image1 = card1.get('image_url_hi_res')
    image1 = image1.replace(
        'https://images.pokemontcg.io/',
        'images/')

    app = Flask(__name__)

    @app.route('/')
    def process_compareform():
        return render_template('cardcompare.tpl',
                               card0=card0, card1=card1,
                               image0=image0, image1=image1,
                               result=card0)

    @app.route('/', methods=['POST'])
    def my_form_post():
        text = request.form['text']
        processed_text = text.upper()
        return processed_text

    app.run(debug=True, use_reloader=False)


def shutdown_flask_server():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()


def review_cards_manually(card0, card1, matchrecord):
    """
    matchrecord contains a mismatch_fields structure of the forms
       'mismatch_fields': {field: [{'score': fuzzyscore,
                                  'vals':[card1val, cardval],
                                  'index': int}
    return struct = {
    'matched' : 'True', 'False', 'Quit' or 'Error'
    'review': [id, id]
    'errors': [{'id': cardid,
                'field': field_to_fix,
                'index': index_in_field,
                'newvalue': new_text},]
    }
    """
    # logging_tree.printout()

    # Nasty Global for moving data between flask route handler and calling
    # function
    returnstruct = {}

    # Get images
    image0 = card0.get('image_url_hi_res')
    image0 = image0.replace(
        'https://images.pokemontcg.io/',
        'images/')
    image1 = card1.get('image_url_hi_res')
    image1 = image1.replace(
        'https://images.pokemontcg.io/',
        'images/')

    app = Flask(__name__)
    app.secret_key = 'the development key'

    @app.route('/', methods=['GET'])
    def show_compareform():
        form = create_compare_form(matchrecord=matchrecord)
        return render_template('cardcompare.tpl',
                               card0=card0, card1=card1,
                               image0=image0, image1=image1,
                               diffs=matchrecord, form=form)

    # TODO - I currently split the handling into a different route because
    # when using the same route previously, when using webbrowser to send
    # safari to the same location, it would warn of resubmitting data.

    @app.route('/process_compare', methods=['POST'])
    def process_compareform():
        logger.info('inside /process_compare')
        # this form object will be populated with the submitted information
        form = create_compare_form(request.form, matchrecord=matchrecord)
        # Build the returnstruct
        if form.quit.data:
            returnstruct['matched'] = 'Quit'
        elif form.no_match.data:
            returnstruct['matched'] = 'False'
        else:
            returnstruct['matched'] = 'True'

            # initilaize card error list
            returnstruct['errors'] = []

            # make sure t   here is a selection for each entry - TODO
            # should do this in the javascript
            for key, value in matchrecord.items():
                formdata = getattr(form, key)
                # formdata.data will be 'None' if nothing was selected *bad*
                if formdata.data == 'None':
                    returnstruct['matched'] = 'Error'
                    shutdown_flask_server()
                    return "Nothing Selected, returning Error"
                logger.info('still inside')
                if formdata.data == 'select_0':
                    returnstruct['errors'].append({'id': card1.get(
                        'id'), 'field': key, 'index': matchrecord[key][0]['index'], 'newvalue':
                        matchrecord[key][0]['vals'][0]})
                elif formdata.data == 'select_1':
                    returnstruct['errors'].append({'id': card0.get(
                        'id'), 'field': key, 'index': matchrecord[key][0]['index'], 'newvalue':
                        matchrecord[key][0]['vals'][1]})
                else:
                    # Should never happen, neither selected.
                    shutdown_flask_server()
                    raise ValueError('Bad return from CompareForm')

        # if form.flag_for_edits.data:

        logger.debug('no_match = {}'.format(form.no_match.data))
        logger.debug('process = {}'.format(form.process_changes.data))
        logger.debug('quit = {}'.format(form.quit.data))
        logger.debug('flags = {}'.format(form.flag_for_edits.data))
        for key, value in matchrecord.items():
            formdata = getattr(form, key)
            logger.debug('choice on {} = {}'.format(key, formdata.data))

        shutdown_flask_server()
        logger.info('Flask server has been shut down')
        return "Changes submitted, waiting for next record"

    # Workaround apple bug (see: https://bugs.python.org/issue30392)
    # webbrowser.open('http://localhost:5000/', autoraise=True)
    webbrowser.get('safari').open('http://localhost:5000/', autoraise=True)
    app.run(debug=True, use_reloader=False)
    logger.debug('Finished review manually processing, returning {}'
                 .format(returnstruct))
    return(returnstruct)
