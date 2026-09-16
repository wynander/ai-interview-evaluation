import { type NextRequest, NextResponse } from "next/server";

import { checkAuth, chaosEvaluation, servicesPool } from "@/src/lib/services-shared";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ customerId: string }> },
): Promise<NextResponse> {
  const auth = checkAuth(request);
  if (auth) return auth;
  const flake = chaosEvaluation(request);
  if (flake) return flake;
  const { customerId } = await params;
  // Flaw: sometimes plain-text 500 on unknown IDs instead of JSON 404.
  const result = await servicesPool().query("SELECT * FROM customers WHERE upper(customer_id) = upper($1)", [
    customerId.trim(),
  ]);
  const row = result.rows[0];
  if (!row) {
    if (Math.random() < 0.5) {
      return new NextResponse(`no customer ${customerId}`, {
        status: 500,
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }
    return NextResponse.json({ detail: `no customer ${customerId}` }, { status: 404 });
  }
  return NextResponse.json(row);
}
