import React from "react";
import CytoscapeComponent from "react-cytoscapejs";

interface Props {
  elements: { nodes: any[]; edges: any[] };
}

export const SubgraphGraph: React.FC<Props> = ({ elements }) => {
  return (
    <CytoscapeComponent
      elements={[...elements.nodes, ...elements.edges]}
      style={{ width: "100%", height: "400px" }}
      layout={{ name: "breadthfirst" }}
    />
  );
};
