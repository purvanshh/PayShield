import networkx as nx


class GraphDB:
    def __init__(self):
        self.graph = nx.MultiDiGraph()

    def add_node(self, node_id: str, node_type: str, features: dict):
        pass

    def add_edge(self, u: str, v: str, edge_type: str, **attrs):
        pass

    def get_ego_graph(self, node_id: str, hops: int = 2) -> nx.MultiDiGraph:
        pass
