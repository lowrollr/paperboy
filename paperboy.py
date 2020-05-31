import os
import re
import discord
from dotenv import load_dotenv
import alpaca_trade_api as alpaca
from datetime import datetime, timedelta
import time
import csv
import pymongo
import json
import requests

#set up python env (used to access server environment variables)
load_dotenv()

#set up mongo client
mongo_client = pymongo.MongoClient('mongodb+srv://dbAdmin:'+os.getenv('DB_PASS')+'@paperboy-cluster-owzvv.gcp.mongodb.net/test?retryWrites=true&w=majority')
db = mongo_client.get_default_database()

#grab the accounts table
accounts = db['Accounts']
db_prices = db['Prices']

#set up regex to recognize discord chat commands
sell_order_regex = re.compile('^\!sell (.*) (.*)')
buy_order_regex = re.compile('^\!buy (.*) (.*)')
price_regex = re.compile('^\!price (.*)')
week_format_regex = re.compile('^([0-6])\/.*')

#grab discord tokens from env
TOKEN = os.getenv('DISCORD_TOKEN')
SERVER = os.getenv('DISCORD_SERVER')

#initialize discord client
client = discord.Client()



#initialize alpaca api
api = alpaca.REST(os.getenv('API_KEY'), os.getenv('SECRET_KEY'), os.getenv('ENDPOINT_URL'))
clock = api.get_clock()

#create ticker-name -> company name dict
my_ticker_names = {}
my_data = requests.get('https://api.iextrading.com/1.0/ref-data/symbols').json()
for x in my_data:
    my_ticker_names[x['symbol']] = x['name']

def get_prices():
    return db_prices.find_one({})

#gets the account corresponding to a given player id
def get_account_info(player):
    target_account = accounts.find_one({'player_id': player})
    #if the player doesn't have an account in the database, create one for them
    if not target_account:
        my_json = {'player_id': player, 'balance': 1000000, 'positions': {}, 'history': {'weekday': {}, 'everyday': {}}}
        accounts.insert_one(my_json)
        return my_json
    return target_account

#log servers that bot connects to on startup
@client.event
async def on_ready():
    for my_server in client.guilds:
        print('Bot connected to discord on server: ' + str(my_server))
        
#listens for and matches specific messages (the important bit)
@client.event
async def on_message(message):
    #if the author of the message is the client user, ignore it 
    #(this prevents the bot reacting to messages that it itself sends)
    if message.author == client.user:
        return 
    #price command
    if '!price' in message.content:
        #match to price command regex
        msg = price_regex.match(str(message.content))
        if msg != None:
            #grab the ticker and coerce it to all upppercase
            ticker = msg.group(1).upper()
            price_day = 0.0
            try:
                if clock.is_open:
                    price_day = api.get_barset(ticker, 'day', limit=1)[ticker][0].c
                else:
                    price_day = api.get_barset(ticker, 'day', limit=2)[ticker][0].c
                price = get_prices()[ticker]
            except IndexError:
                await message.channel.send('Invalid ticker! Could not retrieve info for ' + ticker)
                return
            diff = float(price) - float(price_day)
            perc_change = ((float(price) / float(price_day)) - 1.00) * 100.0
            my_perc_str = ''
            my_price_str = ''
            my_color = 0xFF0000
            if diff > 0.0:
                my_color = 0x00FF00
                my_perc_str += '+'
                my_price_str += '+'
            my_price_str += str(round(diff, 2))
            my_perc_str += str(round(perc_change, 4)) + '%'
            thumb_str = 'https://s3.polygon.io/logos/' + ticker.lower() + '/logo.png'
            if ticker == 'MSFT':
                thumb_str = 'https://eodhistoricaldata.com/img/logos/US/MSFT.png'
            my_embed = discord.Embed(timestamp=message.created_at, color=my_color)
            my_embed.set_author(name=my_ticker_names[ticker])
            my_embed.set_thumbnail(url=thumb_str)
            my_embed.add_field(name='**'+ticker+'**', value=my_price_str)
            my_embed.add_field(name='**'+str(price)+'**', value=my_perc_str)
            await message.channel.send(embed=my_embed)
            
        else:
            await message.channel.send('Invalid command!')
        
    elif '!sell' in message.content:
        msg = sell_order_regex.match(str(message.content))
        if msg != None:
            price = 0.00
            my_prices = get_prices()
            ticker = msg.group(1).upper()
            amnt_msg_group = 2
            try:
                price = my_prices[ticker]
            except KeyError:
                try:
                    amnt_msg_group = 1
                    ticker = msg.group(2).upper()
                    price = my_prices[ticker]
                except KeyError:
                    await message.channel.send('Invalid ticker! Please use !sell <ticker> <amount> or !sell <amount> <ticker>')
                    return
            if price != None:
                val = -1
                try:
                    val = int(msg.group(amnt_msg_group))
                except ValueError:
                    await message.channel.send('Invalid amount! Please use !sell <ticker> <amount> or !sell <amount> <ticker>')
                    return
                info = get_account_info(message.author.id)
                positions = info['positions']
                amount = int(positions[ticker]['amount'])
                amount_balance = float(positions[ticker]['balance'])
                account_balance = float(info['balance'])
                if ticker in positions:
                    avg_price = amount_balance / amount
                    if val <= amount:
                        total_sell_price = val * float(price)
                        if val == amount:
                            del positions[ticker]
                        gain_per_share = round(float(price) - avg_price, 2)
                        amount -= val
                        amount_balance -= total_sell_price
                        my_message = 'Sell Order Executed! ' + str(val) + ' shares of ' + ticker + ' were sold for $' + str(price) + ' each, for a '
                        if gain_per_share < 0:
                            my_message += 'loss'
                        else:
                            my_message += 'gain'
                        my_message += ' of $' + str(abs(gain_per_share)) + ' per share, or ' + str(abs(gain_per_share * val)) + ' total ( ' + str(round(100.0*(gain_per_share/avg_price), 2)) + '% )'
                        await message.channel.send(my_message)
                        if positions:
                            if amount:
                                positions[ticker]['amount'] = amount
                                positions[ticker]['balance'] = amount_balance
                        accounts.update_one({'player_id': message.author.id}, {'$set': {'positions': positions}})
                        accounts.update_one({'player_id': message.author.id}, {'$set': {'balance': account_balance + total_sell_price}})
                    else:
                        await message.channel.send(message.guild.name + ' only owns ' + str(positions[ticker]['amount']) + ' shares of ' + ticker + ', cannot sell ' + str(val) + ' shares!')
                else:
                    await message.channel.send(message.guild.name + ' does not own any positions in ' + ticker + '!')                   
            else:
                await message.channel.send('Invalid amount! Please use !sell <ticker> <amount> or !sell <amount> <ticker>')
            
        else:
            await message.channel.send('Invalid command! Please use !sell <ticker> <amount> or !sell <amount> <ticker>')


    elif '!buy' in message.content:
        msg = buy_order_regex.match(str(message.content))
        if msg != None:
            price = 0.00
            my_prices = get_prices()
            ticker = msg.group(1).upper()
            amnt_msg_group = 2
            try:
                price = my_prices[ticker]
            except KeyError:
                try:
                    amnt_msg_group = 1
                    ticker = msg.group(2).upper()
                    price = my_prices[ticker]
                except KeyError:
                    await message.channel.send('Invalid ticker! Please use !buy <ticker> <amount> or !buy <amount> <ticker>')
                    return
            if price != None:
                val = -1
                try:
                    val = int(msg.group(amnt_msg_group))
                except ValueError:
                    await message.channel.send('Invalid amount! Please use !buy <ticker> <amount> or !buy <amount> <ticker>')
                    return
                total_value = price * val
                info = get_account_info(message.author.id)
                positions = info['positions']
                account_balance = float(info['balance'])
                if total_value > account_balance:
                    await message.channel.send('Not enough funds, account balance is $' + str(account_balance) + ', but this trade requires $' + str(total_value))
                    return
                else:
                    if ticker in positions:
                        positions[ticker]['amount'] += val
                        positions[ticker]['balance'] += total_value
                    else:
                        positions[ticker] = {}
                        positions[ticker]['amount'] = val
                        positions[ticker]['balance'] = total_value
                    accounts.update_one({'player_id': message.author.id}, {'$set': {'positions': positions}})
                    accounts.update_one({'player_id': message.author.id}, {'$set': {'balance': account_balance - total_value}})
                    await message.channel.send('Buy Order executed! ' + str(val) + ' shares of ' + ticker + ' were purchased for $' + str(price) + ' each!')
            else:
                await message.channel.send('Invalid ticker! Please use !buy <ticker> <amount> or !buy <amount> <ticker>')
        else:
            await message.channel.send('Invalid command! Please use !buy <ticker> <amount> or !buy <amount> <ticker>')

    elif '!account' in message.content:
        info = get_account_info(message.author.id)
        total_account_value = info['balance']
        my_prices = get_prices()
        my_stocks_str = ''
        total_delta = 0.0
        for p in info['positions']:
            amount = info['positions'][p]['amount']
            pos_balance = info['positions'][p]['balance']
            cur_price = my_prices[p]
            total_account_value += amount * cur_price
            if clock.is_open:
                price_day = api.get_barset(p, 'day', limit=1)[p][0].c
            else:
                price_day = api.get_barset(p, 'day', limit=2)[p][0].c
            
            delta = cur_price - price_day
            total_delta += delta * amount
            
            if delta > 0.0:
                my_stocks_str += '🟢 '
                my_delta = '+' + str(round(delta, 2))
                my_perc = '+' + str(round(((delta/price_day)*100.0), 2))
            else:
                my_stocks_str += '🔴 '
                my_delta = str(round(delta, 2))
                my_perc = str(round(((delta/price_day)*100.0), 2))
            if cur_price - pos_balance > 0.0:
                my_bal = '+' + str(round(cur_price*amount - pos_balance, 2))
                my_perc_ch = '+' + str(round((cur_price*amount - pos_balance) / cur_price*amount, 2))
            else:
                my_bal = str(round(cur_price*amount - pos_balance, 2))
                my_perc_ch = str(round((cur_price*amount - pos_balance) / cur_price*amount, 2))
            my_stocks_str += '**' + p + ' | ' + my_delta + '  ' + my_perc + '%**\n'
            my_stocks_str += '> *' + str(amount) + ' Positions | ' + my_bal + '  ' + my_perc_ch + '%*\n'
        if total_delta > 0.0:
            my_color = 0x00FF00
            my_tot_delta = '+'+ str(round(total_delta, 2))
        else:
            my_color = 0xFF0000
            my_tot_delta = str(round(total_delta, 2))
        my_stocks_str += '\n**BUYING POWER ' + str(round(info['balance'], 2)) +'**\n'
        my_stocks_str += '**ACCOUNT VALUE ' + str(round(total_account_value, 2)) + '  ' + my_tot_delta +'**\n'
        my_embed = discord.Embed(timestamp=message.created_at, color=my_color, description=my_stocks_str)
        my_embed.set_author(name='**TRADING ACCOUNT SUMMARY -- ' + str(message.author).upper() + '**')
        await message.channel.send(embed=my_embed)
    elif '!help' in message.content:
        my_message = "!account: displays account balance, buying power, and current held positions\n!buy : If able, purchases X shares of a given ticker for it's current price\n!sell : If able, sells X shares of a given ticker from your server's portfolio\n!price : Get the current price of a given ticker\nAll ticker names and prices are referenced from NASDAQ."
        await message.channel.send(my_message)



    
        

def start_discord_client():    
    client.run(TOKEN)

if __name__ == '__main__':
    start_discord_client()
