import os
import re
import discord
from dotenv import load_dotenv
import alpaca_trade_api as alpaca
from datetime import datetime
import time
import csv
import pymongo
import json
import requests

load_dotenv()
client = pymongo.MongoClient('mongodb+srv://dbAdmin:'+os.getenv('DB_PASS')+'@paperboy-cluster-owzvv.gcp.mongodb.net/test?retryWrites=true&w=majority')
db = client.get_default_database()
accounts = db['Accounts']

sell_order_regex = re.compile('^\!sell (.*) (.*)')
buy_order_regex = re.compile('^\!buy (.*) (.*)')
price_regex = re.compile('^\!price (.*)')


scores = {}


TOKEN = os.getenv('DISCORD_TOKEN')
SERVER = os.getenv('DISCORD_SERVER')
client = discord.Client()


api = alpaca.REST(os.getenv('API_KEY'), os.getenv('SECRET_KEY'), os.getenv('ENDPOINT_URL'))
clock = api.get_clock()

my_ticker_names = {}
my_data = requests.get('https://api.iextrading.com/1.0/ref-data/symbols').json()
for x in my_data:
    my_ticker_names[x['symbol']] = x['name']


def get_account_info(player):
    target_account = accounts.find_one({'player_id': player})
    if not target_account:
        my_json = {'player_id': player, 'balance': 1000000, 'positions': {}}
        accounts.insert_one(my_json)
        return my_json
    return target_account


@client.event
async def on_ready():
    for my_server in client.guilds:
        print('Bot connected to discord on server: ' + str(my_server))
        


@client.event
async def on_message(message):
    if message.author == client.user:
        return 
    if '!price' in message.content:
        msg = price_regex.match(str(message.content))
        if msg != None:
            ticker = msg.group(1).upper()
            price_day = 0.0
            if clock.is_open:
                price_day = api.get_barset(ticker, 'day', limit=2)[ticker][0].c
            else:
                price_day = api.get_barset(ticker, 'day', limit=1)[ticker][0].c
            price = api.get_barset(ticker, 'minute', limit=1)[ticker][0].c
            if price != None:
                diff = float(price) - float(price_day)
                perc_change = (float(price) / float(price_day)) - 1.00
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
                my_embed = discord.Embed( timestamp=message.created_at, color=my_color)
                my_embed.set_author(name=my_ticker_names[ticker])
                my_embed.set_thumbnail(url=thumb_str)
                my_embed.add_field(name='**'+ticker+'**', value=my_price_str)
                my_embed.add_field(name='**'+str(price)+'**', value=my_perc_str)
                await message.channel.send(embed=my_embed)
            else:
                await message.channel.send('Invalid ticker! Could not retrieve info for ' + ticker)
        else:
            await message.channel.send('Invalid command!')
        
    elif '!sell' in message.content:
        msg = sell_order_regex.match(str(message.content))
        if msg != None:
            ticker = msg.group(1).upper()
            ticker_info = api.get_barset(ticker, 'minute', limit=1)[ticker]
            amnt_msg_group = 2
            if not ticker_info:
                ticker = msg.group(2).upper()
                ticker_info = api.get_barset(ticker, 'minute', limit=1)[ticker]
                amnt_msg_group = 1
                if not ticker_info:
                    await message.channel.send('Invalid ticker! Please use !sell <ticker> <amount> or !sell <amount> <ticker>')
                    return
            price = ticker_info[0].c
            if price != None:
                good_input = True
                val = -1
                try:
                    val = int(msg.group(amnt_msg_group))
                except ValueError:
                    await message.channel.send('Invalid amount! Please use !sell <ticker> <amount> or !sell <amount> <ticker>')
                    good_input = False
                if good_input:
                    info = get_account_info(message.author.id)
                    positions = info['positions']
                    amount = int(positions[ticker]['amount'])
                    amount_balance = float(positions[ticker]['balance'])
                    account_balance = int(info['balance'])
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
            ticker = msg.group(1).upper()
            ticker_info = api.get_barset(ticker, 'minute', limit=1)[ticker]
            amnt_msg_group = 2
            if not ticker_info:
                ticker = msg.group(2).upper()
                ticker_info = api.get_barset(ticker, 'minute', limit=1)[ticker]
                amnt_msg_group = 1
                if not ticker_info:
                    await message.channel.send('Invalid ticker! Please use !buy <ticker> <amount> or !buy <amount> <ticker>')
                    return
            price = ticker_info[0].c
            if price != None:
                good_input = True
                val = -1
                try:
                    val = int(msg.group(amnt_msg_group))
                except ValueError:
                    await message.channel.send('Invalid amount! Please use !buy <ticker> <amount> or !buy <amount> <ticker>')
                    good_input = False
                if good_input:
                    total_value = price * val
                    info = get_account_info(message.author.id)
                    positions = info['positions']
                    account_balance = int(info['balance'])
                    if total_value > account_balance:
                        await message.channel.send('Not enough funds, account balance is $' + str(account_balance) + ', but this trade requires $' + str(total_value))
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
        my_message = '\n' + str(message.author.name) + ' Trading Account Summary:'
        info = get_account_info(message.author.id)
        total_account_value = float(info['balance'])
        my_message += '\nPositions:'
        for x in info['positions']:
            amount = float(info['positions'][x]['amount'])
            orig_pay = float(info['positions'][x]['balance'])
            cur_price = api.get_barset(x, 'minute', limit=1)[x][0].c
            delta = 0
            cur_value = amount * cur_price
            if cur_price != None:
                total_account_value += cur_value
                delta = cur_value - orig_pay
            my_message += '\n ' + str(int(amount)) + ' ' + x + ': ' + str(int(amount)) + 'x' + str(cur_price) + ' = $' + str(round(cur_value, 2)) + '\t'
            if delta < 0:
                my_message += '($'
            else:
                my_message += '(+$'
            my_message += str(round(delta, 2)) + ')\t('
            if delta < 0:
                my_message += ' '
            else:
                my_message += ' +'
            my_message += str(round(100.0*(delta/cur_value), 2)) + '% )'    
        my_message += '\nAccount Buying Power: $' + str(round(info['balance'], 2))
        my_message += '\nTotal Account Value : $' + str(round(total_account_value, 2))
        await message.channel.send(my_message)
    elif '!help' in message.content:
        my_message = "!account: displays account balance, buying power, and current held positions\n!buy : If able, purchases X shares of a given ticker for it's current price\n!sell : If able, sells X shares of a given ticker from your server's portfolio\n!price : Get the current price of a given ticker\nAll ticker names and prices are referenced from NASDAQ."
        await message.channel.send(my_message)
        
client.run(TOKEN)