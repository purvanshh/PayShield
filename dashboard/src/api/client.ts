const BASE_URL = "http://localhost:8000/v1";

export class PayShieldClient {
  private apiKey: string;

  constructor(apiKey: string) {
    this.apiKey = apiKey;
  }

  async scoreTransaction(txn: any) {
    const res = await fetch(`${BASE_URL}/score`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": this.apiKey,
      },
      body: JSON.stringify(txn),
    });
    return res.json();
  }

  async getInvestigation(txnId: string) {
    const res = await fetch(`${BASE_URL}/investigation/${txnId}`, {
      headers: { "X-API-Key": this.apiKey },
    });
    return res.json();
  }
}
