/**
 * auth.ts
 *
 * Auth.js v5 (next-auth@beta) configuration.
 *
 * The Credentials provider calls the FastAPI backend's /api/auth/login
 * endpoint which verifies the password against a bcrypt hash stored in
 * SQLite.  No passwords are stored or compared on the Next.js side.
 */
import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

/** The FastAPI backend URL — used server-side only (not exposed to the browser). */
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [
    Credentials({
      credentials: {
        username: { label: "Username", type: "text" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.username || !credentials?.password) return null;

        try {
          const res = await fetch(`${BACKEND_URL}/api/v1/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              username: credentials.username,
              password: credentials.password,
            }),
          });

          if (!res.ok) return null;

          const user = await res.json();
          // Return the shape NextAuth expects — id must be a string.
          // The backend returns id as an integer; convert it here so that
          // Auth.js stores it correctly as token.sub (JWT subject claim).
          return { id: String(user.id), name: user.name, role: user.role };
        } catch {
          // Backend unreachable — reject the login attempt.
          return null;
        }
      },
    }),
  ],
  callbacks: {
    // Persist role and id into the JWT on first sign-in.
    jwt({ token, user }) {
      if (user) {
        token.role = (user as { role: string }).role;
        // Explicitly mirror user.id into token.sub (Auth.js may already do
        // this, but the custom callback overrides the default, so be explicit).
        token.sub = user.id;
      }
      return token;
    },
    // Expose role and id on session.user for both server and client components.
    session({ session, token }) {
      const u = session.user as { role?: string; id?: string };
      u.role = token.role as string;
      // token.sub is the user's DB id (set above from user.id).
      // The custom session callback replaces Auth.js defaults, so we must
      // copy sub → id explicitly; otherwise session.user.id stays undefined.
      u.id = token.sub;
      return session;
    },
  },
  pages: {
    signIn: "/login",
  },
});
