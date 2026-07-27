import { useEffect, useRef } from "react";

interface GraphNode {
  id: string;
  type: "user" | "merchant" | "device" | "transaction";
  label?: string;
}

interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  layout?: "cose" | "circle";
  height?: number;
}

const NODE_COLORS: Record<string, string> = {
  user: "#3b82f6",
  merchant: "#16a34a",
  device: "#8b5cf6",
  transaction: "#f59e0b",
};

const EDGE_STYLES: Record<string, { style: string; color: string }> = {
  performed: { style: "solid", color: "#94a3b8" },
  to: { style: "dashed", color: "#64748b" },
  used: { style: "dotted", color: "#475569" },
  shared_by: { style: "solid", color: "#dc2626" },
};

export function SubgraphGraph({ nodes, edges, layout = "cose", height = 400 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || typeof window === "undefined") return;

    let cy: any = null;

    const loadCytoscape = async () => {
      try {
        const cytoscape = (await import("cytoscape")).default;
        if (!containerRef.current) return;

        const elements = [
          ...nodes.map((n) => ({
            data: {
              id: n.id,
              label: n.label || `${n.type}_${n.id.slice(0, 6)}`,
              type: n.type,
            },
          })),
          ...edges.map((e) => ({
            data: { source: e.source, target: e.target, type: e.type },
          })),
        ];

        cy = cytoscape({
          container: containerRef.current,
          elements,
          style: [
            {
              selector: "node",
              style: {
                "background-color": (ele: any) => NODE_COLORS[ele.data("type")] || "#94a3b8",
                label: "data(label)",
                "text-valign": "center",
                "text-halign": "center",
                color: "#f8fafc",
                "font-size": 10,
                width: 40,
                height: 40,
              },
            },
            {
              selector: "edge",
              style: {
                "line-color": (ele: any) => EDGE_STYLES[ele.data("type")]?.color || "#64748b",
                "line-style": (ele: any) => EDGE_STYLES[ele.data("type")]?.style || "solid",
                "target-arrow-color": "#64748b",
                "target-arrow-shape": "triangle",
                width: 2,
                "arrow-scale": 0.8,
              },
            },
            {
              selector: "node:selected",
              style: { "border-color": "#f8fafc", "border-width": 3 },
            },
          ],
          layout: { name: layout === "circle" ? "circle" : "cose", animate: true },
          userZoomingEnabled: true,
          userPanningEnabled: true,
        });
      } catch {
        // Cytoscape not available
      }
    };

    loadCytoscape();

    return () => {
      if (cy) cy.destroy();
    };
  }, [nodes, edges, layout]);

  return (
    <div
      ref={containerRef}
      style={{
        width: "100%",
        height,
        background: "#0f172a",
        borderRadius: 8,
        border: "1px solid #1e293b",
      }}
    />
  );
}
