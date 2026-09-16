import { type NextRequest, NextResponse } from "next/server";

import { checkAuth, chaosEvaluation, servicesPool } from "@/src/lib/services-shared";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const auth = checkAuth(request);
  if (auth) return auth;
  const flake = chaosEvaluation(request);
  if (flake) return flake;
  const needle = (request.nextUrl.searchParams.get("search") ?? "").trim().toLowerCase();
  const result = await servicesPool().query("SELECT customer_id, name, email FROM customers");
  let rows = result.rows as Array<{ customer_id: string; name: string; email: string }>;
  if (needle) {
    rows = rows.filter(
      (r) =>
        r.name.toLowerCase().includes(needle) ||
        r.email.toLowerCase().includes(needle) ||
        needle === r.customer_id.toLowerCase(),
    );
  }
  return NextResponse.json({ customers: rows });
}
