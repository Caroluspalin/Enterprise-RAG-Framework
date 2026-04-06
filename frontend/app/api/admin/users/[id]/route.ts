/**
 * DELETE /api/admin/users/:id — delete a user
 */
import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { deleteUser } from "@/lib/admin";

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const session = await auth();
  if (!session || (session.user as { role?: string }).role !== "admin") {
    return NextResponse.json({ detail: "Forbidden" }, { status: 403 });
  }

  const { id } = await params;

  try {
    await deleteUser(id);
    return NextResponse.json({ message: "User deleted." });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to delete user";
    return NextResponse.json({ detail: msg }, { status: 400 });
  }
}
