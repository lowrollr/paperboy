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


def get_account_info(guild):
    return accounts.find_one({'server': guild})


@client.event
async def on_ready():
    for my_server in client.guilds:
        print('Bot connected to discord on server: ' + str(my_server))
        doc = accounts.find_one({'server': str(my_server)})
        if not doc:
            accounts.insert_one({'server': str(my_server), 'balance': 1000000, 'positions': {}})
        


@client.event
async def on_message(message):
    if message.author == client.user:
        return 
    if '!price' in message.content:
        msg = price_regex.match(str(message.content))
        if msg != None:
            ticker = msg.group(1)
            price = api.get_barset(ticker, 'minute', limit=1)[ticker][0].c
            if price != None:
                await message.channel.send(ticker + ' price = $' + str(price))
            else:
                await message.channel.send('Invalid ticker! Could not retrieve info for ' + ticker)
        else:
            await message.channel.send('Invalid command!')
        
    elif '!sell' in message.content:
        msg = sell_order_regex.match(str(message.content))
        if msg != None:
            ticker = msg.group(1)
            ticker_info = api.get_barset(ticker, 'minute', limit=1)[ticker]
            if ticker_info:
                price = ticker_info[0].c
                if price != None:
                    good_input = True
                    val = -1
                    try:
                        val = int(msg.group(2))
                    except ValueError:
                        await message.channel.send('Invalid amount! Please use !sell <ticker> <amount>')
                        good_input = False
                    if good_input:
                        info = get_account_info(message.guild.name)
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
                                my_message += ' of $' + str(abs(gain_per_share)) + ' ( ' + str(round(100.0*(gain_per_share/avg_price), 2)) + '% )'
                                await message.channel.send(my_message)
                                if positions:
                                    positions[ticker]['amount'] = amount
                                    positions[ticker]['balance'] = amount_balance
                                accounts.update_one({'server': message.guild.name}, {'$set': {'positions': positions}})
                            else:
                                await message.channel.send(message.guild.name + ' only owns ' + str(positions[ticker]['amount']) + ' shares of ' + ticker + ', cannot sell ' + str(val) + ' shares!')
                        else:
                            await message.channel.send(message.guild.name + ' does not own any positions in ' + ticker + '!')                   
                else:
                    await message.channel.send('Invalid amount! Please use !sell <ticker> <amount>')
            else:
                await message.channel.send('Invalid ticker! Please use !sell <ticker> <amount>')
        else:
            await message.channel.send('Invalid command! Please use !sell <ticker> <amount>')


    elif '!buy' in message.content:
        msg = buy_order_regex.match(str(message.content))
        if msg != None:
            ticker = msg.group(1)
            ticker_info = api.get_barset(ticker, 'minute', limit=1)[ticker]
            if ticker_info:
                price = ticker_info[0].c
                if price != None:
                    good_input = True
                    val = -1
                    try:
                        val = int(msg.group(2))
                    except ValueError:
                        await message.channel.send('Invalid amount! Please use !buy <ticker> <amount>')
                        good_input = False
                    if good_input:
                        total_value = price * val
                        info = get_account_info(message.guild.name)
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
                            accounts.update_one({'server': message.guild.name}, {'$set': {'positions': positions}})
                            accounts.update_one({'server': message.guild.name}, {'$set': {'balance': account_balance - total_value}})
                            await message.channel.send('Buy Order executed! ' + str(val) + ' shares of ' + ticker + ' were purchased for $' + str(price) + ' each!')
                else:
                    await message.channel.send('Invalid ticker! Please use !buy <ticker> <amount>')
            else:
                await message.channel.send('Invalid ticker! Please use !buy <ticker> <amount>')
        else:
            await message.channel.send('Invalid command! Please use !buy <ticker> <amount>')

    elif '!account' in message.content:
        my_message = '\n' + str(message.guild.name) + ' Trading Account Summary:'
        info = get_account_info(message.guild.name)
        total_account_value = int(info['balance'])
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

client.run(TOKEN)