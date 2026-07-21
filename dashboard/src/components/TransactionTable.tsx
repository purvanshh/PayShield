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
}

export const TransactionTable: React.FC<Props> = ({ transactions }) => {
  return (
    <table>
      <thead>
        <tr>
          <th>Transaction ID</th>
          <th>User</th>
          <th>Amount</th>
          <th>Decision</th>
          <th>Fraud Probability</th>
        </tr>
      </thead>
      <tbody>
        {transactions.map((txn) => (
          <tr key={txn.txn_id}>
            <td>{txn.txn_id}</td>
            <td>{txn.user_id}</td>
            <td>{txn.amount}</td>
            <td>{txn.decision}</td>
            <td>{txn.fraud_probability.toFixed(4)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};
