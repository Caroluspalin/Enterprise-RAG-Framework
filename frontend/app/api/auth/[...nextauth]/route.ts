/**
 * app/api/auth/[...nextauth]/route.ts
 *
 * Catches all /api/auth/* requests (sign-in, sign-out, session, CSRF token…)
 * and delegates them to Auth.js. No logic lives here — everything is in auth.ts.
 */
import { handlers } from "@/auth";

export const { GET, POST } = handlers;
