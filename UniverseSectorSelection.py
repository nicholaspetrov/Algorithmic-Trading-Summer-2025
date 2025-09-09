# region imports
from AlgorithmImports import *
# endregion

class VolatilityBreakout(QCAlgorithm):

    # parameters
    min_price = 10
    max_price = 1_000
    portfolio_size = 10
    cash = 100_000
    input_start_date = {"year": 2024, "month": 1, "day": 1}
    input_end_date = {"year": 2024, "month": 1, "day": 10}
    asset_type = ["ETF", "Share", "Index"]
    sector_mapping = {
        101: "Basic Materials",
        102: "Consumer Cyclical",
        103: "Financial Services",
        104: "Real Estate",
        205: "Consumer Defensive",
        206: "Healthcare",
        207: "Utilities",
        308: "Communication Services",
        309: "Energy",
        310: "Industrials",
        311: "Technology"
    }

    def initialize(self) -> None:
        # dates
        self.set_start_date(**self.input_start_date)
        self.set_end_date(**self.input_end_date)

        # initial account value
        self.set_cash(self.cash)

        # warm-up
        self.settings.automatic_indicator_warm_up = True

        # universe settings
        self.universe_settings.leverage = Security.NULL_LEVERAGE
        self.universe_settings.data_normalization_mode = DataNormalizationMode.RAW
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.schedule.on(self.date_rules.every_day())

        # select equities that have the most dollar trading volume
        # self.add_universe(self.universe.dollar_volume.top(10))
        self.add_universe_selection(
            FundamentalUniverseSelectionModel(
            universe_settings=self.universe_settings,
            selector=self.selection
            )
        )

        # brokerage
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.CASH)

        # When a new asset enters the universe, seed its current price so you can trade it right away.
        self.set_security_initializer(
            BrokerageModelSecurityInitializer(self.brokerage_model, FuncSecuritySeeder(self.get_last_known_prices))
        )

    def selection(self, fundamental: list[Fundamental]) -> list[Symbol]:

        sector_codes = list(self.sector_mapping.keys())
        valid_assets = [
            x for x in fundamental 
            if x.has_fundamental_data
            and x.asset_classification.morningstar_sector_code in sector_codes
            and x.market == "usa"
            ]

        sector_groups = {}
        for asset in valid_assets:
            sector = asset.asset_classification.morningstar_sector_code
            if sector not in sector_groups:
                sector_groups[sector] = []
            sector_groups[sector].append(asset)

        selected_symbols = []
        for sector in sector_codes:
            if sector in sector_groups:
                sorted_assets = sorted(
                    [x for x in sector_groups[sector] if self.min_price < x.price <= self.max_price],
                    key=lambda x: x.dollar_volume,
                    reverse=True
                    )
                top_assets = sorted_assets[:self.portfolio_size]
                selected_symbols.extend([x.symbol for x in top_assets])

                sector_name = self.sector_mapping.get(sector, "Unkown")
                self.debug(f"Selected {len(top_assets)} from {sector_name}: {[asset.symbol.value for asset in top_assets]}")
        
        return selected_symbols

    def on_securities_changed(self, changes: SecurityChanges) -> None:
        """
        React to an event when the universe adds and removes assets.
        :param changes:
        :type changes:
        :return:
        :rtype: None
        """
        # Iterate through the added securities.
        for security in changes.added_securities:
            self.debug(f"{self.time} universe added  : {security.symbol.value} {security.price:,}")


        # Iterate through the removed securities.
        for security in changes.removed_securities:
            self.debug(f"{self.time} universe removed: {security.symbol.value}")

            if security.invested:
                self.liquidate(f"Portfolio liquidated: {security.symbol.value}")

        securities = self.active_securities
        # self.debug(f"\n{self.time} active securities: {[s.key.value for s in securities]}")
        self.debug(f"\n{self.time} active securities: {[len(securities)]}")

    def on_data(self, data: Slice):
        # Ensure there are TradeBar objects in the current slice
        if not data.bars:
            return
