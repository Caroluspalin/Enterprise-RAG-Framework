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
          const res = await fetch(`${BACKEND_URL}/api/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              username: credentials.username,
              password: credentials.password,
            }),
          });

          if (!res.ok) return null;

          const user = await res.json();
          // Return the shape NextAuth expects — id, name, and our custom role field.
          return { id: user.id, name: user.name, role: user.role };
        } catch {
          // Backend unreachable — reject the login attempt.
          return null;
        }
      },
    }),
  ],
  callbacks: {
    // Copy role from the User object into the JWT when the token is first created.
    jwt({ token, user }) {
      if (user) token.role = (user as { role: string }).role;
      return token;
    },
    // Expose role on session.user so both server and client components can read it.
    session({ session, token }) {
      (session.user as { role?: string }).role = token.role as string;
      return session;
    },
  },
  pages: {
    signIn: "/login",
  },
});
