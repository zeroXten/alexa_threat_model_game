from pprint import pprint
import logging
from flask import Flask, render_template
from flask_ask import Ask, question, statement, session
import yaml
import random
import boto3
import uuid
from datetime import datetime

logger = logging.getLogger("flask_ask")
logger.setLevel(logging.DEBUG)

app = Flask(__name__)
ask = Ask(app, "/")

#####################################################################
# Session helper functions
#####################################################################

class AlexaSession():

    @staticmethod
    def set_handler(handler):
        session.attributes['handler'] = handler

    @staticmethod
    def get_handler():
        if 'handler' in session.attributes:
            return session.attributes['handler']
        else:
            return None

    @staticmethod
    def user_id():
        return session.user.userId

#####################################################################
# Classes
#####################################################################

class EopGame:
    def __init__(self):
        self.user_data = {}

    def load_table(self):
        table_name = 'eop_games'
        logger.debug("loading table {0}".format(table_name))

        client = boto3.client('dynamodb')
        resource = boto3.resource('dynamodb')
    
        table_exists = False
        try:
            tabledescription = client.describe_table(TableName=table_name)
            table_exists = True
        except Exception as e:
            if "Requested resource not found: Table" in str(e):
                self.table = resource.create_table(
                    TableName = table_name,
                    KeySchema = [
                        {'AttributeName': 'user_id', 'KeyType': 'HASH'}
                    ],
                    AttributeDefinitions = [
                        {'AttributeName': 'user_id', 'AttributeType': 'S'}
                    ],
                    ProvisionedThroughput = {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                )
                self.table.meta.client.get_waiter('table_exists').wait(TableName=table_name)
                table_exists = True
            else:
                raise

        self.table = resource.Table(table_name)

    def load_data(self):
        logger.info("loading data")
        try:
            response = self.table.get_item(Key={'user_id': AlexaSession.user_id()})
        except ClientError as e:
            logger.error(e.response['Error']['Message'])
        else:
            if 'Item' in response:
                self.user_data = response['Item']
                logger.debug("loaded existig data for user_id {0}".format(AlexaSession.user_id()))
            else:
                game_id = self.new_game_id()
                game_name = "Quick Start"
                self.user_data['user_id'] = AlexaSession.user_id()
                self.user_data['current_game_id'] = game_id
                self.user_data['games'] = {
                    game_id: {
                        'name': game_name,
                        'seed': self.new_seed(),
                        'index': 0,
                        'created': datetime.now().isoformat(),
                        'updated': datetime.now().isoformat()
                    }
                }
                self.table.put_item(Item=self.user_data)
                logger.debug("created new data for user_id".format(AlexaSession.user_id()))

    def load(self):
        self.load_table()
        self.load_data()

    def save(self):
        self.table.put_item(Item=self.user_data)

    def game_id(self):
        return self.user_data['current_game_id']

    def current_game(self):
        return self.user_data['games'][self.game_id()]

    def new_game_id(self):
        return str(uuid.uuid4())

    def new_seed(self):
        return random.randint(0,2**32-1)

    def seed(self):
        return self.current_game()['seed']

    def reset_seed(self):
        game_id = self.game_id()
        self.user_data['games'][self.game_id()]['seed'] = self.new_seed()
        self.save()

    def name(self):
        return self.current_game()['name']

    def index(self):
        return int(self.current_game()['index'])

    def reset_index(self):
        self.user_data['games'][self.game_id()]['index'] = 0
        self.save()
        
    def next_index(self):
        self.user_data['games'][self.game_id()]['index'] += 1
        self.save()
        return self.index()

    def previous_index(self):
        self.user_data['games'][self.game_id()]['index'] -= 1
        self.save()
        return self.index()

class EopCardDeck:
    def load_cards(self):
        self.cards = []
        logger.debug("reading cards.yaml")
        with open("cards.yaml") as fh:
            card_data = yaml.load(fh)
            for suit in card_data["suit_order"]:
                for rank in card_data["rank_order"]:
                    if rank in card_data["suits"][suit]:
                        self.cards.append({
                            "rank": rank,
                            "rank_word": card_data["ranks"][rank],
                            "description": card_data["suits"][suit][rank],
                            "suit": suit
                        })

    def load(self, game):
        self.game = game
        self.load_cards()
        self.restore()

    def shuffle(self, seed):
        self.deck = list(self.cards)
        random.Random(seed).shuffle(self.deck)

    def restore(self):
        seed = self.game.seed()
        logger.debug("restoring deck with seed {0}".format(seed))
        self.shuffle(seed)

    def card_at_index(self, index):
        return self.deck[index]

    def card(self):
        index = self.game.index()
        logger.debug("return card at index {0}".format(index))
        return self.deck[index]

    def next_card(self):
        if self.game.index() < len(self.cards)-1:
            self.game.next_index()
        return self.card()

    def previous_card(self):
        if self.game.index() > 0:
            self.game.previous_index()
        return self.card()

game = EopGame()
deck = EopCardDeck()

#####################################################################
# Intent functions
#####################################################################

@ask.intent("AMAZON.YesIntent")
def alexa_yes():
    handler = AlexaSession.get_handler()

    if handler == 'help_info':
        return alexa_how_to_play()
    elif handler == 'how_to_play_question':
        return alexa_how_to_play()
    elif handler == 'how_to_play_info':
        return alexa_threat_modelling()
    elif handler == 'threat_modelling_question':
        return alexa_threat_modelling()
    elif handler == 'threat_modelling_info':
        return alexa_about_game()
    elif handler == 'about_game_question':
        return alexa_about_game()
    else:
        return statement(render_template('nohandler'))

@ask.intent("AMAZON.NoIntent")
def alexa_no():
    handler = AlexaSession.get_handler()

    if handler == 'help_info':
        return threat_modelling_question()
    elif handler == 'how_to_play_question':
        return threat_modelling_question()
    elif handler == 'how_to_play_info':
        return about_game_question()
    elif handler == 'threat_modelling_question':
        return about_game_question()
    elif handler == 'threat_modelling_info':
        return statement(render_template('end_of_help'))
    elif handler == 'about_game_question':
        return statement(render_template('end_of_help'))
    else:
        return statement(render_template('nohandler'))

@ask.intent("AMAZON.HelpIntent")
def alexa_help():
    AlexaSession.set_handler('help_info')
    return question(render_template('help_info'))

@ask.intent("HowToPlayIntent")
def alexa_how_to_play():
    AlexaSession.set_handler('how_to_play_info')
    return question(render_template('how_to_play_info'))

@ask.intent("ThreatModellingIntent")
def alexa_threat_modelling():
    AlexaSession.set_handler('threat_modelling_info')
    return question(render_template('threat_modelling_info'))

def threat_modelling_question():
    AlexaSession.set_handler('threat_modelling_question')
    return question(render_template('threat_modelling_question'))

@ask.intent('AboutGameIntent')
def alexa_about_game():
    AlexaSession.set_handler('about_game_info')
    return statement(render_template('about_game_info'))

def about_game_question():
    AlexaSession.set_handler('about_game_question')
    return question(render_template('about_game_question'))

@ask.intent("RandomCardIntent")
def alexa_random_card():
    AlexaSession.set_handler('random_card')
    global game
    global deck
    deck.load_cards()
    deck.shuffle(game.new_seed())

    msg = render_template('random_card', card=deck.card_at_index(0))
    return statement(msg)

@ask.launch
def alexa_launch():
    AlexaSession.set_handler('launch')
    global game
    global deck
    game.load()
    deck.load(game)

    msg = render_template('welcome', name=game.name(), prefix='first', card=deck.card())
    return statement(msg)

@ask.intent("CurrentCardIntent")
def alexa_current_card():
    AlexaSession.set_handler('current_card')
    global game
    global deck
    game.load()
    deck.load(game)

    msg = render_template('card', prefix='current', card=deck.card())
    return statement(msg)

@ask.intent("AMAZON.NextIntent")
@ask.intent("NextCardIntent")
def alexa_next_card():
    AlexaSession.set_handler('next_card')
    global game
    global deck
    game.load()
    deck.load(game)

    current_card = deck.card()
    new_card = deck.next_card()
    if new_card == current_card:
        msg = render_template('no_cards', prefix='last', card=current_card)
    else:
        msg = render_template('next_card', prefix='new', card=new_card)
    return statement(msg)
    
@ask.intent("AMAZON.PreviousIntent")
@ask.intent("PreviousCardIntent")
def alexa_previous_card():
    AlexaSession.set_handler('previous_card')
    global game
    global deck
    game.load()
    deck.load(game)

    current_card = deck.card()
    new_card = deck.previous_card()
    if new_card == current_card:
        msg = render_template('first_card', prefix='first', card=current_card)
    else:
        msg = render_template('previous_card', prefix='new', card=new_card)
    return statement(msg)

@ask.intent("RestartGameIntent")
def alexa_restart_game():
    AlexaSession.set_handler('restart_game')
    global game
    global deck
    game.load()
    deck.load(game)

    game.reset_index()
    game.reset_seed()
    deck.restore()
    
    msg = render_template('restart_game', name=game.name(), prefix='first', card=deck.card())
    return statement(msg)
    
#####################################################################
# Main
#####################################################################

if __name__ == '__main__':
    app.run(debug=True)
