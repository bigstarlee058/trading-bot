import configparser
import datetime
from ib_insync import IB, util, ExecutionFilter
import pandas as pd
from core_error import handle_ex

class IBKRTradesFetcher:
    """Fetches trade history from Interactive Brokers using ib_insync"""

    def __init__(self, account=None):
        self.config = configparser.ConfigParser()
        self.config.read('config.ini')
        self.account = account
        self.conn = None

    def get_account_config(self, account):
        """Get account configuration with group support"""
        account_config = self.config[account]
        if 'group' in account_config:
            group = account_config['group']
            group_config = self.config[group]
            # Merge group config into account config, account config takes precedence
            merged_config = {**group_config, **account_config}
            return merged_config
        return account_config

    def connect(self, account=None):
        """Connect to IBKR for the specified account"""
        try:
            if account:
                self.account = account

            if not self.account:
                raise ValueError("Account must be specified")

            aconfig = self.get_account_config(self.account)

            self.conn = IB()
            self.conn.connect(
                aconfig['host'],
                int(aconfig['port']),
                clientId=999,  # Use a different client ID to avoid conflicts
                timeout=20
            )
            print(f"Connected to IBKR for account {self.account}")
            return True
        except Exception as e:
            handle_ex(e, context=f"ibkr_connect_{self.account}", service="webapp")
            raise

    def disconnect(self):
        """Disconnect from IBKR"""
        try:
            if self.conn and self.conn.isConnected():
                self.conn.disconnect()
                print("Disconnected from IBKR")
        except Exception as e:
            handle_ex(e, context="ibkr_disconnect", service="webapp")

    def get_fills(self, days_back=7):
        """
        Get execution fills from IBKR for the past N days
        Returns a list of dicts with fill information
        """
        try:
            if not self.conn or not self.conn.isConnected():
                raise Exception("Not connected to IBKR")

            # Request fills
            fills = self.conn.fills()

            # Filter by date
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days_back)

            fills_data = []
            for fill in fills:
                fill_time = fill.time

                # Convert to datetime if it's a string
                if isinstance(fill_time, str):
                    fill_time = datetime.datetime.fromisoformat(fill_time.replace('Z', '+00:00'))

                if fill_time.replace(tzinfo=None) < cutoff_date:
                    continue

                fills_data.append({
                    'time': fill_time,
                    'symbol': fill.contract.symbol,
                    'exchange': fill.execution.exchange,
                    'side': fill.execution.side,
                    'shares': fill.execution.shares,
                    'price': fill.execution.price,
                    'avgPrice': fill.execution.avgPrice,
                    'execId': fill.execution.execId,
                    'orderId': fill.execution.orderId,
                    'account': fill.execution.acctNumber,
                    'commission': fill.commissionReport.commission if fill.commissionReport else None,
                    'realizedPNL': fill.commissionReport.realizedPNL if fill.commissionReport else None,
                })

            # Sort by time descending
            fills_data.sort(key=lambda x: x['time'], reverse=True)

            return fills_data

        except Exception as e:
            handle_ex(e, context="get_fills", service="webapp")
            raise

    def get_trades(self, days_back=7):
        """
        Get trade orders from IBKR for the past N days
        Returns a list of dicts with trade information
        """
        try:
            if not self.conn or not self.conn.isConnected():
                raise Exception("Not connected to IBKR")

            # Request trades
            trades = self.conn.trades()

            # Filter by date
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days_back)

            trades_data = []
            for trade in trades:
                # Get the log entries to find the order time
                log_time = None
                if trade.log:
                    # Use the first log entry time as the order time
                    log_time = trade.log[0].time

                if log_time:
                    if isinstance(log_time, str):
                        log_time = datetime.datetime.fromisoformat(log_time.replace('Z', '+00:00'))
                    if log_time.replace(tzinfo=None) < cutoff_date:
                        continue

                trades_data.append({
                    'orderId': trade.order.orderId,
                    'symbol': trade.contract.symbol,
                    'action': trade.order.action,
                    'totalQuantity': trade.order.totalQuantity,
                    'orderType': trade.order.orderType,
                    'lmtPrice': trade.order.lmtPrice if hasattr(trade.order, 'lmtPrice') else None,
                    'auxPrice': trade.order.auxPrice if hasattr(trade.order, 'auxPrice') else None,
                    'status': trade.orderStatus.status,
                    'filled': trade.orderStatus.filled,
                    'remaining': trade.orderStatus.remaining,
                    'avgFillPrice': trade.orderStatus.avgFillPrice,
                    'lastFillTime': trade.log[-1].time if trade.log else None,
                    'account': trade.order.account,
                })

            # Sort by orderId descending
            trades_data.sort(key=lambda x: x['orderId'], reverse=True)

            return trades_data

        except Exception as e:
            handle_ex(e, context="get_trades", service="webapp")
            raise

    def get_executions_historical(self, days_back=7):
        """
        Get historical executions using reqExecutions with a filter
        This gets more historical data than the fills() method
        Returns a list of dicts with execution information
        """
        try:
            if not self.conn or not self.conn.isConnected():
                raise Exception("Not connected to IBKR")

            # Create execution filter for the time period
            # IBKR expects time in format: yyyymmdd-hh:mm:ss (but we'll use just date)
            start_date = datetime.datetime.now() - datetime.timedelta(days=days_back)
            time_filter = start_date.strftime('%Y%m%d-00:00:00')

            # Create filter
            exec_filter = ExecutionFilter()
            exec_filter.time = time_filter

            # Request executions
            print(f"Requesting executions since {time_filter}...")
            executions = self.conn.reqExecutions(exec_filter)

            print(f"Received {len(executions)} executions from IBKR")

            exec_data = []
            for fill in executions:
                exec_time = fill.time

                # Convert to datetime if it's a string
                if isinstance(exec_time, str):
                    exec_time = datetime.datetime.fromisoformat(exec_time.replace('Z', '+00:00'))

                exec_data.append({
                    'time': exec_time,
                    'symbol': fill.contract.symbol,
                    'exchange': fill.execution.exchange,
                    'side': fill.execution.side,
                    'shares': fill.execution.shares,
                    'price': fill.execution.price,
                    'avgPrice': fill.execution.avgPrice,
                    'execId': fill.execution.execId,
                    'orderId': fill.execution.orderId,
                    'account': fill.execution.acctNumber,
                    'commission': fill.commissionReport.commission if fill.commissionReport else None,
                    'realizedPNL': fill.commissionReport.realizedPNL if fill.commissionReport else None,
                })

            # Sort by time descending
            exec_data.sort(key=lambda x: x['time'], reverse=True)

            return exec_data

        except Exception as e:
            handle_ex(e, context="get_executions_historical", service="webapp")
            raise

    def get_executions(self, days_back=7):
        """
        Get execution details from IBKR for the past N days
        Returns a list of dicts with execution information
        """
        try:
            if not self.conn or not self.conn.isConnected():
                raise Exception("Not connected to IBKR")

            # Request executions
            executions = self.conn.executions()

            # Filter by date
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days_back)

            exec_data = []
            for exec in executions:
                exec_time = exec.time

                # Convert to datetime if it's a string
                if isinstance(exec_time, str):
                    exec_time = datetime.datetime.fromisoformat(exec_time.replace('Z', '+00:00'))

                if exec_time.replace(tzinfo=None) < cutoff_date:
                    continue

                exec_data.append({
                    'time': exec_time,
                    'symbol': exec.contract.symbol,
                    'exchange': exec.execution.exchange,
                    'side': exec.execution.side,
                    'shares': exec.execution.shares,
                    'price': exec.execution.price,
                    'execId': exec.execution.execId,
                    'orderId': exec.execution.orderId,
                    'account': exec.execution.acctNumber,
                })

            # Sort by time descending
            exec_data.sort(key=lambda x: x['time'], reverse=True)

            return exec_data

        except Exception as e:
            handle_ex(e, context="get_executions", service="webapp")
            raise

    def analyze_slippage(self, fills_data, signals_data):
        """
        Compare IBKR fills with our internal signals to identify slippage/gaps

        Args:
            fills_data: List of fill dicts from get_fills()
            signals_data: List of signal dicts from database

        Returns:
            List of dicts with slippage analysis
        """
        analysis = []

        # Group fills by symbol and time proximity
        for fill in fills_data:
            fill_symbol = fill['symbol']
            fill_time = fill['time']
            fill_price = fill['price']

            # Find matching signals within 5 minutes of the fill
            for signal in signals_data:
                signal_symbol = signal.get('ticker', '').replace('1!', '')  # Handle futures suffix
                signal_time = signal.get('timestamp')

                if isinstance(signal_time, str):
                    signal_time = datetime.datetime.fromisoformat(signal_time.replace('Z', '+00:00'))

                # Check if symbol matches and time is within 5 minutes
                if signal_symbol == fill_symbol:
                    time_diff = abs((fill_time.replace(tzinfo=None) - signal_time.replace(tzinfo=None)).total_seconds())

                    if time_diff <= 300:  # 5 minutes
                        # Try to get expected price from signal
                        order_price = signal.get('order_price')

                        slippage_pct = None
                        if order_price and order_price > 0:
                            slippage_pct = ((fill_price - order_price) / order_price) * 100

                        analysis.append({
                            'fill_time': fill_time,
                            'signal_time': signal_time,
                            'time_diff_seconds': time_diff,
                            'symbol': fill_symbol,
                            'side': fill['side'],
                            'shares': fill['shares'],
                            'expected_price': order_price,
                            'fill_price': fill_price,
                            'slippage_pct': slippage_pct,
                            'commission': fill.get('commission'),
                            'realizedPNL': fill.get('realizedPNL'),
                        })

        # Sort by fill time descending
        analysis.sort(key=lambda x: x['fill_time'], reverse=True)

        return analysis
