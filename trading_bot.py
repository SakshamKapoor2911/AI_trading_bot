from lumibot.brokers import Alpaca
from lumibot.backtesting import YahooDataBacktesting
from lumibot.strategies.strategy import Strategy
from lumibot.traders import Trader
from datetime import datetime
from alpaca_trade_api import REST
from timedelta import Timedelta
from dotenv import load_dotenv
import os
import requests
from finbert_utils import estimate_sentiment
import time

load_dotenv()

ALPACA_CREDS = {
    "API_KEY": os.getenv("API_KEY"),
    "API_SECRET": os.getenv("API_SECRET"),
    "PAPER": True #Set to True if not using real money, change to False when trading with real currency
}

class MLTrader(Strategy):
    #initializes bot with 1. symbol for benchmark, 2. sleeptime and 3. set empty size for prev trades 
    def initialize(self, symbol:str="SPY", cash_at_risk:float=0.5): 
        self.symbol = symbol
        self.sleeptime = "24H"
        self.last_trade = None
        self.cash_at_risk = cash_at_risk
        self.api = REST(base_url=os.getenv("BASE_URL"), key_id=os.getenv("API_KEY"), secret_key=os.getenv("API_SECRET"))
        
    #dynamically adjusts the size of trades (number of shares to buy/sell) based on 1. available cash, 2. last price 
    def position_sizing(self):
        cash = self.get_cash()
        last_price = self.get_last_price(self.symbol)
        quantity = round(cash * self.cash_at_risk / last_price,0)
        return cash, last_price, quantity

    #get and return today's date and three days prior
    def get_dates(self): 
        today = self.get_datetime()
        three_days_prior = today - Timedelta(days=3)
        return today.strftime('%Y-%m-%d'), three_days_prior.strftime('%Y-%m-%d')

    def get_sentiment(self):
        today, three_days_prior = self.get_dates()
        url = os.getenv("BASE_URL")
        params = {
            "symbols": self.symbol,
            "start": three_days_prior,
            "end": today
        }
        headers = {
            "APCA-API-KEY-ID": os.getenv("API_KEY"),
            "APCA-API-SECRET-KEY": os.getenv("API_SECRET")
        }
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 429:  # Too many requests
            time.sleep(10)  # Wait 60 seconds before retrying
            response = requests.get(url, params=params, headers=headers)
    
        if response.status_code == 200:
            news_data = response.json()
            #print("News Response: ", news_data)
            headlines = [article["headline"] for article in news_data["news"]] 
            # summary = [article["summary"] for article in news_data["news"]] 
            # content = [article["content"] for article in news_data["news"]] 
            # text_for_sentiment = f"{headline}"
            # print("News Response:", headlines)
            probability, sentiment = estimate_sentiment(headlines)
            return probability, sentiment
        else:
            print(f"Error: {response.status_code}")
            return []
        # news = self.api.get_news(symbol=self.symbol, start=three_days_prior, end= today)
        # news = [ev.__dict__["_raw"]["headline"] for ev in news]
    

    def on_trading_iteration(self):
        cash, last_price, quantity = self.position_sizing()
        probability, sentiment = self.get_sentiment() 
        
        # extra check to ensure we have more cash available than the price of trade we want to buy
        if cash > last_price:
                if sentiment == "positive" and probability > .999:
                    if self.last_trade == "sell":
                        self.sell_all()
                    order = self.create_order(
                        self.symbol,
                        quantity,
                        "buy",
                        type="bracket",
                        # setting a limit to sell stock at 20% profit if it rises
                        take_profit_price = last_price * 1.20,
                        # setting a limit to sell stock before losses exceed 5%
                        stop_loss_price = last_price * 0.95
                    )
                    self.submit_order(order)
                    self.last_trade = "buy"
                elif sentiment == "negative" and probability > .999:
                    if self.last_trade != "sell":  # Only sell if not already in a short position
                        if self.last_trade == "buy":
                            self.sell_all()
                        order = self.create_order(
                            self.symbol,
                            quantity,
                            "sell",
                            type="bracket",
                            # setting a limit to sell stock at 10% profit if it rises
                            take_profit_price = last_price * 0.8,
                            # setting a limit to sell stock before losses exceed 10%
                            stop_loss_price = last_price * 1.05 
                        )
                        self.submit_order(order)
                        self.last_trade = "sell"


start_date = datetime(2018, 1, 1)
end_date = datetime(2019, 1, 1)

broker = Alpaca(ALPACA_CREDS)
strategy = MLTrader(name='mlstrategy', broker=broker, 
                    parameters={"symbol":"SPY", "cash_at_risk":0.5})

strategy.backtest(
    YahooDataBacktesting,
    start_date,
    end_date,
    parameters={"symbol":"SPY", "cash_at_risk":.5}
)