/**
 * DELETE /api/admin/api-keys/:id — revoke an API key
 */
import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { revokeApiKey } from "@/lib/admin";

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
    await revokeApiKey(id);
    return NextResponse.json({ message: "API key revoked." });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to revoke API key";
    return NextResponse.json({ detail: msg }, { status: 400 });
  }
}
