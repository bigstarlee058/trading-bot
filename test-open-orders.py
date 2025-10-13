#!/usr/bin/env python3
"""Test script to see what open orders IBKR returns"""

import configparser
from ib_insync import IB
import time

def get_account_config(account, config):
    """Get account config with group inheritance"""
    account_config = config[account]
    if 'group' in account_config:
        group = account_config['group']
        group_config = config[group]
        merged_config = {**group_config, **account_config}
        return merged_config
    return dict(account_config)

# Get first account
config = configparser.ConfigParser()
config.read('config.ini')

account_list_str = config['bot-live']['accountsfull']
account_numbers = [acc.strip() for acc in account_list_str.split(',')]

# Test with first account
account_num = account_numbers[0]
aconfig = get_account_config(account_num, config)

print(f"Testing with account: {account_num}")
print(f"Connecting to {aconfig['host']}:{aconfig['port']}...")

ib = IB()
ib.connect(aconfig['host'], int(aconfig['port']), clientId=997, timeout=20)

print("\n1. Testing ib.openTrades():")
open_trades = ib.openTrades()
print(f"   Found {len(open_trades)} trades")
for trade in open_trades:
    print(f"   - {trade.order.action} {trade.order.totalQuantity} {trade.contract.symbol} @ {trade.order.lmtPrice if hasattr(trade.order, 'lmtPrice') else 'MKT'}")
    print(f"     Status: {trade.orderStatus.status}, Account: {trade.order.account}")

print("\n2. Testing ib.reqOpenOrders():")
ib.reqOpenOrders()
time.sleep(2)  # Give it time to receive
open_orders = ib.openOrders()
print(f"   Found {len(open_orders)} orders")
for order in open_orders:
    print(f"   - Order ID: {order.orderId}, Account: {order.account}")

print("\n3. Testing ib.reqAllOpenOrders():")
ib.reqAllOpenOrders()
time.sleep(2)  # Give it time to receive
all_trades = ib.openTrades()
print(f"   Found {len(all_trades)} trades")
for trade in all_trades:
    print(f"   - {trade.order.action} {trade.order.totalQuantity} {trade.contract.symbol}")
    print(f"     Status: {trade.orderStatus.status}, Account: {trade.order.account}")

print("\n4. Checking positions:")
positions = ib.positions(account_num)
print(f"   Found {len(positions)} positions")
for pos in positions:
    print(f"   - {pos.contract.symbol}: {pos.position} shares")

ib.disconnect()
