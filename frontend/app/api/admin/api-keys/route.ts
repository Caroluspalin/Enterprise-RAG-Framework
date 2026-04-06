/**
 * GET  /api/admin/api-keys?user_id=...  — list API keys for a user
 * POST /api/admin/api-keys              — create a new API key
 */
import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { listApiKeys, createApiKey } from "@/lib/admin";

async function requireAdmin() {
  const session = await auth();
  if (!session || (session.user as { role?: string }).role !== "admin") {
    return false;
  }
  return true;
}

export async function GET(request: Request) {
  if (!(await requireAdmin())) {
    return NextResponse.json({ detail: "Forbidden" }, { status: 403 });
  }
  const { searchParams } = new URL(request.url);
  const userId = searchParams.get("user_id");
  if (!userId) {
    return NextResponse.json({ detail: "user_id is required" }, { status: 400 });
  }
  try {
    const keys = await listApiKeys(userId);
    return NextResponse.json({ api_keys: keys });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to list API keys";
    return NextResponse.json({ detail: msg }, { status: 500 });
  }
}

export async function POST(request: Request) {
  if (!(await requireAdmin())) {
    return NextResponse.json({ detail: "Forbidden" }, { status: 403 });
  }
  try {
    const body = await request.json();
    const key = await createApiKey(body.user_id, body.label);
    return NextResponse.json(key, { status: 201 });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to create API key";
    return NextResponse.json({ detail: msg }, { status: 400 });
  }
}
