import { type NextRequest, NextResponse } from "next/server";

import { checkAuth, chaosEvaluation, servicesPool } from "@/src/lib/services-shared";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ subscriptionId: string }> },
): Promise<NextResponse> {
  const auth = checkAuth(request);
  if (auth) return auth;
  const flake = chaosEvaluation(request);
  if (flake) return flake;
  const { subscriptionId } = await params;
  const result = await servicesPool().query("SELECT * FROM subscriptions WHERE subscription_id = $1", [
    subscriptionId.trim(),
  ]);
  const row = result.rows[0];
  if (!row) {
    return NextResponse.json({ detail: `no subscription ${subscriptionId}` }, { status: 404 });
  }
  return NextResponse.json(row);
}
