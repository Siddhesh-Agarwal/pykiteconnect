import logging
from kiteconnect import KiteConnect
from kiteconnect.types import Variety, Exchange, TransactionType, Product, OrderType

logging.basicConfig(level=logging.DEBUG)

kite = KiteConnect(api_key="your_api_key")

# Redirect the user to the login url obtained
# from kite.login_url(), and receive the request_token
# from the registered redirect url after the login flow.
# Once you have the request_token, obtain the access_token
# as follows.

data = kite.generate_session("request_token_here", api_secret="your_secret")
kite.set_access_token(data["access_token"])

# Place an order
try:
    order_id = kite.place_order(
        variety=Variety.REGULAR,
        exchange=Exchange.NSE,
        tradingsymbol="INFY",
        transaction_type=TransactionType.BUY,
        quantity=1,
        product=Product.CNC,
        order_type=OrderType.MARKET,
    )

    logging.info("Order placed. ID is: {}".format(order_id))
except Exception as e:
    logging.info("Order placement failed: {}".format(e))

# Fetch all orders
kite.orders()

# Get instruments
kite.instruments()

# Place an mutual fund order
kite.place_mf_order(tradingsymbol="INF090I01239", transaction_type=TransactionType.BUY, amount=5000, tag="mytag")

# Cancel a mutual fund order
kite.cancel_mf_order(order_id="order_id")

# Get mutual fund instruments
kite.mf_instruments()
