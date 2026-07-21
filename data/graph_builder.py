import networkx as nx
import pandas as pd


class HeterogeneousGraphBuilder:
    def __init__(self):
        self.graph = nx.MultiDiGraph()

    def build_from_transactions(self, df: pd.DataFrame):
        pass

    def to_pyg_data(self):
        pass
