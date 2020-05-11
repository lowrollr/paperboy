![paperboy_logo](https://raw.githubusercontent.com/marshingjay/paperboy/master/paperboy.PNG)
Paperboy is a discord bot that manages a shared paper-trading portfolio for each discord server it's added to, allowing for 24/7 simulated trading with no real-life stakes. Paperboy is built with Python, the Python Discord API, the Alpaca Trading API, and MongoDB. Paperboy is currently in development but will soon be publicly available for free. 

### Use the following chat commands to interface with the bot:

!account: displays account balance, buying power, and current held positions

!buy <ticker> <amount>: If able, purchases X shares of a given ticker for it's current price
  
!sell <ticker> <amount>: If able, sells X shares of a given ticker from your server's portfolio
  
!price <ticker>: Get the current price of a given ticker
  
All ticker names and prices are referenced from NASDAQ.

### Future features include:
* Local Leaderboard
* Server Leaderboard
* Options Trading (?)
* Charts and Figures
* Expanded DB Cluster capacity to handle higher traffic
