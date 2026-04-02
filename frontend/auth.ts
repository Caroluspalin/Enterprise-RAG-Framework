/**
 * auth.ts
 *
 * Auth.js v5 (next-auth@beta) configuration.
 *
 * Uses a Credentials provider with two hard-coded demo users so the MVP can
 * be demoed immediately without a database. In production, replace the
 * DEMO_USERS lookup with a real DB query and hash passwords with bcrypt.
 */
import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

// Hard-coded demo users — replace with a DB lookup in production.
// Passwords are compared in plain text here; use bcrypt hashes in production.
const DEMO_USERS = [
  { id: "1", name: "User",  username: "user",  password: "user123",  role: "user"  },
  { id: "2", name: "Admin", username: "admin", password: "admin123", role: "admin" },
] as const;

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [
    Credentials({
      credentials: {
        username: { label: "Username", type: "text" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const user = DEMO_USERS.find(
          (u) =>
            u.username === credentials?.username &&
            u.password === credentials?.password
        );
        // Returning null causes NextAuth to reject the credentials.
        if (!user) return null;
        // Only return fields we want stored in the token — never the password.
        return { id: user.id, name: user.name, role: user.role };
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
