import { type NextRequest, NextResponse } from "next/server";

import { chaosEnabled, checkAuth, chaosEvaluation, servicesPool, sleep } from "@/src/lib/services-shared";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const auth = checkAuth(request);
  if (auth) return auth;
  const flake = chaosEvaluation(request);
  if (flake) return flake;
  // Offset pagination over 15k rows: slow for C999.
  // Naive clients fetch only page 1 (50 of 15k). Handle pagination client-side.
  if (chaosEnabled(request)) {
    await sleep(100 + Math.random() * 500);
  }
  const params = request.nextUrl.searchParams;
  const customerId = params.get("customer_id") ?? "";
  const limit = Math.min(Number(params.get("limit") ?? 50), 200);
  const cursor = Number(params.get("cursor") ?? 0);
  const pool = servicesPool();
  const counted = await pool.query("SELECT count(*) AS n FROM orders WHERE upper(customer_id) = upper($1)", [
    customerId.trim(),
  ]);
  const total = Number(counted.rows[0]?.n ?? 0);
  const result = await pool.query(
    "SELECT * FROM orders WHERE upper(customer_id) = upper($1) ORDER BY placed_on DESC LIMIT $2 OFFSET $3",
    [customerId.trim(), limit, cursor],
  );
  const rows = result.rows.map((row) => ({ ...row, total_usd: Number(row.total_usd) }));
  const nextCursor = cursor + limit < total ? cursor + limit : null;
  return NextResponse.json({ orders: rows, total, next_cursor: nextCursor });
}
