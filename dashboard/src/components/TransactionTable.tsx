import { useState } from "react";

interface Column<T> {
  key: string;
  label: string;
  render?: (row: T) => React.ReactNode;
  sortable?: boolean;
}

interface Props<T> {
  data: T[];
  columns: Column<T>[];
  onRowClick?: (row: T) => void;
  pageSize?: number;
}

export function TransactionTable<T extends Record<string, unknown>>({
  data,
  columns,
  onRowClick,
  pageSize = 20,
}: Props<T>) {
  const [page, setPage] = useState(1);
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const sorted = [...data].sort((a, b) => {
    if (!sortKey) return 0;
    const av = a[sortKey];
    const bv = b[sortKey];
    if (typeof av === "number" && typeof bv === "number") {
      return sortDir === "asc" ? av - bv : bv - av;
    }
    return sortDir === "asc"
      ? String(av).localeCompare(String(bv))
      : String(bv).localeCompare(String(av));
  });

  const totalPages = Math.ceil(sorted.length / pageSize);
  const pageData = sorted.slice((page - 1) * pageSize, page * pageSize);

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const probColor = (val: number) => {
    if (val > 0.85) return "#dc2626";
    if (val > 0.5) return "#f59e0b";
    return "#16a34a";
  };

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid #334155" }}>
            {columns.map((col) => (
              <th
                key={col.key}
                onClick={() => col.sortable && handleSort(col.key)}
                style={{
                  padding: "8px 12px",
                  textAlign: "left",
                  cursor: col.sortable ? "pointer" : "default",
                  color: "#94a3b8",
                  fontWeight: 600,
                  fontSize: 12,
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                }}
              >
                {col.label}
                {sortKey === col.key && (sortDir === "asc" ? " ▲" : " ▼")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {pageData.map((row, i) => (
            <tr
              key={i}
              onClick={() => onRowClick?.(row)}
              style={{
                borderBottom: "1px solid #1e293b",
                cursor: onRowClick ? "pointer" : "default",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "#1e293b")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
            >
              {columns.map((col) => {
                const raw = row[col.key];
                const isProb = col.key === "fraud_probability";
                return (
                  <td key={col.key} style={{ padding: "8px 12px" }}>
                    {col.render ? (
                      col.render(row)
                    ) : isProb && typeof raw === "number" ? (
                      <span style={{ color: probColor(raw), fontWeight: 600 }}>
                        {(raw * 100).toFixed(1)}%
                      </span>
                    ) : (
                      String(raw ?? "")
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 16 }}>
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            style={{ padding: "4px 12px", background: "#1e293b", border: "1px solid #334155", borderRadius: 4, color: "#f8fafc", cursor: "pointer" }}
          >
            Prev
          </button>
          <span style={{ padding: "4px 12px", color: "#94a3b8" }}>
            {page} / {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            style={{ padding: "4px 12px", background: "#1e293b", border: "1px solid #334155", borderRadius: 4, color: "#f8fafc", cursor: "pointer" }}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
