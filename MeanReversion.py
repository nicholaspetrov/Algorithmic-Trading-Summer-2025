# region imports
from AlgorithmImports import *
from Selection.FundamentalUniverseSelectionModel import FundamentalUniverseSelectionModel
from scipy.stats import norm, zscore
# endregion

class FatFluorescentYellowTapir(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2021, 1, 1)
        self.set_cash(100000)
        self.universe_settings.resolution = Resolution.DAILY

        self.add_universe_selection(LiquidUniverseSelectionModel())
        
        self.add_alpha(MeanReversionAlphaModel())

        self.set_portfolio_construction(EqualWeightingPortfolioConstructionModel())
        
        self.set_risk_management(NullRiskManagementModel())

        self.set_execution(ImmediateExecutionModel())


class LiquidUniverseSelectionModel(FundamentalUniverseSelectionModel):
    def __init__(self):
        super().__init__(True, None)
        self.last_month = -1 # New universe once a month

    def select_coarse(self, algorithm, coarse):
        if self.last_month == algorithm.time.month:
            return Universe.UNCHANGED
        self.last_month = algorithm.time.month

        filtered = [x for x in coarse if x.has_fundamental_data and x.price > 10]
        sorted_by_dollar_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_dollar_volume[:100]]
    
    def select_fine(self, algorithm, fine):
        return [f.symbol for f in fine]


class MeanReversionAlphaModel(AlphaModel):
    def __init__(self, lookback=30, resolution=Resolution.DAILY):
        self.lookback = lookback
        self.resolution = resolution
        self.name = 'MeanReversionAlphaModel'
        self.securities = {}

    def update(self, algorithm, data):
        # Fetch history on our universe
        df = algorithm.history(list(self.securities.keys()), self.lookback, self.resolution)
        if df.empty:
            return []

        # Make all of them into a single time index
        df = df.close.unstack(level=0)
    
        # Calculate the 30-day EMA and standard deviation
        ema = df.ewm(span=30).mean()
        std = df.std()
        
        # Long signals: price is less than 1 std below EMA
        long_classifier = df.le(ema.subtract(std)).iloc[-1]
        # Short signals: price is more than 1 std above EMA
        short_classifier = df.ge(ema.add(std)).iloc[-1]
        
        insights = []

        # Process long signals
        if long_classifier.any():
            long_z_score = df.apply(zscore)[[long_classifier.index[i] for i in range(long_classifier.size) if long_classifier.iloc[i]]]
            long_magnitude = -long_z_score * std / df
            long_confidence = (-long_z_score).apply(norm.cdf)
            long_magnitude = long_magnitude.iloc[-1].fillna(0)
            long_confidence = long_confidence.iloc[-1].fillna(0)
            long_weight = long_confidence - 1 / (long_magnitude + 1)
            long_weight = long_weight[long_weight > 0].fillna(0)
            long_sum = np.sum(long_weight)
            if long_sum > 0:
                long_weight = long_weight / long_sum
                for symbol, magnitude, confidence, weight in zip(long_weight.index, long_magnitude, long_confidence, long_weight):
                    insights.append(Insight.price(symbol, timedelta(days=1), InsightDirection.UP, magnitude, confidence, None, weight))

        # Process short signals
        if short_classifier.any():
            short_z_score = df.apply(zscore)[[short_classifier.index[i] for i in range(short_classifier.size) if short_classifier.iloc[i]]]
            short_magnitude = short_z_score * std / df  # Positive z-score for downward movement
            short_confidence = short_z_score.apply(norm.cdf)  # Confidence for downward movement
            short_magnitude = short_magnitude.iloc[-1].fillna(0)
            short_confidence = short_confidence.iloc[-1].fillna(0)
            short_weight = short_confidence - 1 / (short_magnitude + 1)
            short_weight = short_weight[short_weight > 0].fillna(0)
            short_sum = np.sum(short_weight)
            if short_sum > 0:
                short_weight = short_weight / short_sum
                for symbol, magnitude, confidence, weight in zip(short_weight.index, short_magnitude, short_confidence, short_weight):
                    insights.append(Insight.price(symbol, timedelta(days=1), InsightDirection.DOWN, magnitude, confidence, None, weight))
        
        return insights

    def on_securities_changed(self, algorithm, changes):
        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol in self.securities:
                del self.securities[symbol]
        
        for security in changes.added_securities:
            symbol = security.symbol
            self.securities[symbol] = None
