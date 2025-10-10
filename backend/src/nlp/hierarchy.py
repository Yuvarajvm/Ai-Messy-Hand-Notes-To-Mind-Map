import networkx as nx

def build_hierarchy_tree(G_cooc: nx.Graph, root: str = None) -> nx.DiGraph:
    if G_cooc.number_of_nodes() == 0:
        return nx.DiGraph()
    if root is None:
        root = sorted(G_cooc.degree, key=lambda x: x[1], reverse=True)[0][0]

    # Connect isolated nodes to root with minimal weight
    for n in list(G_cooc.nodes()):
        if n == root:
            continue
        if not nx.has_path(G_cooc, root, n):
            G_cooc.add_edge(root, n, weight=0.0001)

    T_undirected = nx.maximum_spanning_tree(G_cooc, weight="weight")
    T = nx.DiGraph()
    T.add_nodes_from(T_undirected.nodes(data=True))
    for comp in nx.connected_components(T_undirected):
        comp_root = root if root in comp else list(comp)[0]
        for u, v in nx.bfs_edges(T_undirected, source=comp_root):
            T.add_edge(u, v, weight=G_cooc[u][v].get("weight", 1))
    return T