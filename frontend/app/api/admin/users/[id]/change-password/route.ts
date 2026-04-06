/**
 * POST /api/admin/users/:id/change-password — change a user's password
 */
import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { changePassword } from "@/lib/admin";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const session = await auth();
  if (!session || (session.user as { role?: string }).role !== "admin") {
    return NextResponse.json({ detail: "Forbidden" }, { status: 403 });
  }

  const { id } = await params;

  try {
    const body = await request.json();
    await changePassword(id, body.old_password, body.new_password);
    return NextResponse.json({ message: "Password changed." });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to change password";
    return NextResponse.json({ detail: msg }, { status: 400 });
  }
}
