import React from "react";

interface Transaction {
  txn_id: string;
  user_id: string;
  amount: number;
  decision: string;
  fraud_probability: number;
}

interface Props {
  transactions: Transaction[];
  onSelect: (txn: Transaction) => void;
}

export const TransactionTable: React.FC<Props> = ({ transactions, onSelect }) => {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <thead>
        <tr style={{ backgroundColor: "#f5f5f5", textAlign: "left" }}>
          <th style={thStyle}>Txn ID</th>
          <th style={thStyle}>User</th>
          <th style={thStyle}>Amount</th>
          <th style={thStyle}>Decision</th>
          <th style={thStyle}>Score</th>
        </tr>
      </thead>
      <tbody>
        {transactions.map((txn) => (
          <tr
            key={txn.txn_id}
            onClick={() => onSelect(txn)}
            style={{ cursor: "pointer", borderBottom: "1px solid #eee" }}
          >
            <td style={tdStyle}>{txn.txn_id}</td>
            <td style={tdStyle}>{txn.user_id}</td>
            <td style={tdStyle}>₹{txn.amount.toLocaleString()}</td>
            <td style={tdStyle}>
              <span
                style={{
                  color: txn.decision === "BLOCK" ? "red" : txn.decision === "REVIEW" ? "orange" : "green",
                  fontWeight: 600,
                }}
              >
                {txn.decision}
              </span>
            </td>
            <td style={tdStyle}>{(txn.fraud_probability * 100).toFixed(1)}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};

const thStyle: React.CSSProperties = {
  padding: "10px 12px",
  fontWeight: 600,
  fontSize: "13px",
  textTransform: "uppercase",
  letterSpacing: "0.5px",
};

const tdStyle: React.CSSProperties = {
  padding: "10px 12px",
  fontSize: "14px",
};
