import { type NextRequest, NextResponse } from "next/server";

import { checkAuth, chaosEvaluation, servicesPool } from "@/src/lib/services-shared";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ orderId: string }> },
): Promise<NextResponse> {
  const auth = checkAuth(request);
  if (auth) return auth;
  const flake = chaosEvaluation(request);
  if (flake) return flake;
  const { orderId } = await params;
  const result = await servicesPool().query("SELECT * FROM orders WHERE order_id = $1", [orderId.trim()]);
  const row = result.rows[0];
  if (!row) {
    return NextResponse.json({ detail: `no order ${orderId}` }, { status: 404 });
  }
  return NextResponse.json({ ...row, total_usd: Number(row.total_usd) });
}
