from dotenv import load_dotenv
import pymongo
import os
import datetime
import alpaca_trade_api as alpaca
import time
#set up python env (used to access server environment variables)
load_dotenv()

#set up mongo client
mongo_client = pymongo.MongoClient('mongodb+srv://dbAdmin:'+os.getenv('DB_PASS')+'@paperboy-cluster-owzvv.gcp.mongodb.net/test?retryWrites=true&w=majority')
db = mongo_client.get_default_database()

#grab the accounts table
accounts = db['Accounts']
db_prices = db['Prices']

all_accounts = {}

api = alpaca.REST(os.getenv('API_KEY'), os.getenv('SECRET_KEY'), os.getenv('ENDPOINT_URL'))
clock = api.get_clock()

assets = api.list_assets()
prices = {}
for a in assets:
    if a.symbol == 'SPY':
        print(a.exchange)
    if a.tradable and a.status == 'active' and (a.exchange == 'NASDAQ' or a.exchange == 'ARCA'):
        prices[a.symbol] = 0.00

bars = {}

def read_prices_to_db():
    db_prices.replace_one(filter={}, replacement=prices, upsert=True)
    


def update_prices():
    global prices
    symbols = set()
    counter = 0
    for a in prices:
        counter += 1
        symbols.add(a)
        if counter == 199:
            bars = api.get_barset(symbols=symbols, timeframe='minute', limit=1)
            for b in bars:
                if bars[b]:
                    prices[b] = bars[b][0].c
            symbols = set()
            counter = 0
    bars = api.get_barset(symbols=symbols, timeframe='minute', limit=1)
    for b in bars:
        if bars[b]:
            prices[b] = bars[b][0].c



def get_total_value(account):
    total_balance = float(account['balance'])
    for p in account['positions']:
        total_balance += float( prices[p] * account['positions'][p]['amount'] )
    return total_balance

def update_account_history_min(first):
    global all_accounts
    all_accounts = accounts.find({})
    for a in all_accounts:
        day_of_week = datetime.datetime.today().weekday()
        now = datetime.datetime.now()
        my_val = get_total_value(a)
        if first:
            accounts.update_one({'player_id': a['player_id']}, {'$set': {'history.weekday.' + str(day_of_week) + '/' + str(now.hour) + '/' + str(now.minute): my_val, 'history.everyday.' + str(now.year) + '/' + str(now.month) + '/' + str(now.day): my_val}})
        else:
            accounts.update_one({'player_id': a['player_id']}, {'$set': {'history.weekday.' + str(day_of_week) + '/' + str(now.hour) + '/' + str(now.minute): my_val}})
        
        print('updated account: ' + str(a['player_id']))
            

def collect():
    first = True
    while clock.is_open:
        print('collecting!')
        now = datetime.datetime.now()
        next_1_min = (now.minute)%60
        next_5_min = (now.minute+5)%60
        next_hour = now.hour
        if next_5_min < now.minute:
            next_hour += 1
        done = False
        while(datetime.datetime.now().minute != next_5_min or datetime.datetime.now().hour != next_hour):
            if datetime.datetime.now().minute >= next_1_min%60: 
                print(datetime.datetime.now().minute)
                update_prices()
                if not done:
                    update_account_history_min(first)
                    done = True
                    
                read_prices_to_db()
                next_1_min = datetime.datetime.now().minute + 1
                if first:
                    first = False
    update_prices()
    update_account_history_min(False)    
    read_prices_to_db()
        


while(True):
    now = datetime.datetime.now()
    mrkt_open = now.replace(hour=14, minute=30)
    if mrkt_open == now:
        collect()
    