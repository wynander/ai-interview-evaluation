import { type NextRequest, NextResponse } from "next/server";

import { checkAuth, chaosEvaluation, servicesPool, productAlias, regionAlias } from "@/src/lib/services-shared";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const auth = checkAuth(request);
  if (auth) return auth;
  const flake = chaosEvaluation(request);
  if (flake) return flake;
  const params = request.nextUrl.searchParams;
  const svc = productAlias((params.get("service") ?? "").trim());
  const reg = regionAlias((params.get("region") ?? "").trim());
  const result = await servicesPool().query(
    "SELECT * FROM incidents WHERE lower(service) = lower($1) AND region = $2 AND status = 'active' LIMIT 1",
    [svc, reg],
  );
  const row = result.rows[0];
  return NextResponse.json({ status: row ? "active" : "none", incident: row ?? null });
}
