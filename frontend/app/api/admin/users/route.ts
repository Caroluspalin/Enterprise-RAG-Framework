/**
 * GET  /api/admin/users  — list all users
 * POST /api/admin/users  — create a new user
 *
 * Server-side only: injects INTERNAL_ADMIN_SECRET before calling FastAPI.
 */
import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { listUsers, createUser } from "@/lib/admin";

/** Reject non-admin callers with a 403. */
async function requireAdmin() {
  const session = await auth();
  if (!session || (session.user as { role?: string }).role !== "admin") {
    return false;
  }
  return true;
}

export async function GET() {
  if (!(await requireAdmin())) {
    return NextResponse.json({ detail: "Forbidden" }, { status: 403 });
  }
  try {
    const users = await listUsers();
    return NextResponse.json({ users });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to list users";
    return NextResponse.json({ detail: msg }, { status: 500 });
  }
}

export async function POST(request: Request) {
  if (!(await requireAdmin())) {
    return NextResponse.json({ detail: "Forbidden" }, { status: 403 });
  }
  try {
    const body = await request.json();
    const user = await createUser(
      body.username,
      body.password,
      body.name,
      body.role ?? "user",
    );
    return NextResponse.json(user, { status: 201 });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to create user";
    return NextResponse.json({ detail: msg }, { status: 400 });
  }
}
