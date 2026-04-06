"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "@/components/Toast";
import type { User, ApiKey, ApiKeyWithSecret } from "@/types";

// ---------------------------------------------------------------------------
// "Show once" secret banner — displayed after a key is created
// ---------------------------------------------------------------------------

function SecretBanner({
  rawKey,
  onDismiss,
}: {
  rawKey: string;
  onDismiss: () => void;
}) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(rawKey).then(() => {
      setCopied(true);
      toast("success", "API key copied to clipboard.");
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="rounded-xl border border-amber-700/50 bg-amber-950/40 p-4">
      <p className="mb-2 text-sm font-semibold text-amber-300">
        Copy this key now — you will not see it again!
      </p>
      <div className="flex items-center gap-2">
        <code className="flex-1 break-all rounded-lg bg-slate-900 px-3 py-2 text-xs text-emerald-400">
          {rawKey}
        </code>
        <button
          onClick={handleCopy}
          className="shrink-0 rounded-lg bg-amber-700 px-3 py-2 text-xs font-medium text-white hover:bg-amber-600"
        >
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
      <button
        onClick={onDismiss}
        className="mt-3 text-xs text-slate-400 hover:text-white"
      >
        I have saved this key, dismiss
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Create key modal
// ---------------------------------------------------------------------------

function CreateKeyModal({
  users,
  onClose,
  onCreated,
}: {
  users: User[];
  onClose: () => void;
  onCreated: (key: ApiKeyWithSecret) => void;
}) {
  const [userId, setUserId] = useState(users[0]?.id ?? "");
  const [label, setLabel] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!label.trim() || !userId) return;
    setLoading(true);
    try {
      const res = await fetch("/api/admin/api-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, label: label.trim() }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed" }));
        throw new Error(err.detail);
      }
      const key: ApiKeyWithSecret = await res.json();
      toast("success", `API key "${label}" created.`);
      onCreated(key);
      onClose();
    } catch (err) {
      toast("error", err instanceof Error ? err.message : "Failed to create API key.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        className="w-full max-w-md space-y-4 rounded-xl border border-slate-700 bg-slate-900 p-6"
      >
        <h3 className="text-lg font-semibold text-white">Create API Key</h3>

        <label className="block">
          <span className="text-xs text-slate-400">User (owner)</span>
          <select
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none"
          >
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.username} ({u.role})
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="text-xs text-slate-400">Label (e.g. &quot;Autokauppa widget&quot;)</span>
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            required
            className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
          />
        </label>

        <div className="flex justify-end gap-3 pt-2">
          <button type="button" onClick={onClose} className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:text-white">
            Cancel
          </button>
          <button
            type="submit"
            disabled={loading}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {loading ? "Creating..." : "Create"}
          </button>
        </div>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ApiKeysTab() {
  const [users, setUsers] = useState<User[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<string>("");
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newSecret, setNewSecret] = useState<string | null>(null);

  // Fetch users first so we can select which one's keys to show.
  const fetchUsers = useCallback(async () => {
    try {
      const res = await fetch("/api/admin/users");
      if (!res.ok) throw new Error();
      const data = await res.json();
      setUsers(data.users);
      if (data.users.length > 0 && !selectedUserId) {
        setSelectedUserId(data.users[0].id);
      }
    } catch {
      toast("error", "Failed to load users.");
    }
  }, [selectedUserId]);

  const fetchKeys = useCallback(async (userId: string) => {
    if (!userId) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/admin/api-keys?user_id=${encodeURIComponent(userId)}`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      setKeys(data.api_keys);
    } catch {
      toast("error", "Failed to load API keys.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  useEffect(() => {
    if (selectedUserId) fetchKeys(selectedUserId);
  }, [selectedUserId, fetchKeys]);

  async function handleRevoke(keyId: string) {
    if (!confirm("Revoke this API key? Widgets using it will stop working.")) return;
    setRevokingId(keyId);
    try {
      const res = await fetch(`/api/admin/api-keys/${keyId}`, { method: "DELETE" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed" }));
        throw new Error(err.detail);
      }
      toast("success", "API key revoked.");
      fetchKeys(selectedUserId);
    } catch (err) {
      toast("error", err instanceof Error ? err.message : "Failed to revoke key.");
    } finally {
      setRevokingId(null);
    }
  }

  function handleKeyCreated(key: ApiKeyWithSecret) {
    setNewSecret(key.raw_key);
    fetchKeys(selectedUserId);
  }

  return (
    <div className="space-y-4">
      {/* Secret banner */}
      {newSecret && (
        <SecretBanner rawKey={newSecret} onDismiss={() => setNewSecret(null)} />
      )}

      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          API Keys
        </h2>
        <button
          onClick={() => setShowCreate(true)}
          disabled={users.length === 0}
          className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          + New Key
        </button>
      </div>

      {/* User selector */}
      {users.length > 0 && (
        <label className="block">
          <span className="text-xs text-slate-400">Show keys for user:</span>
          <select
            value={selectedUserId}
            onChange={(e) => setSelectedUserId(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none"
          >
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.username} ({u.role})
              </option>
            ))}
          </select>
        </label>
      )}

      {/* Keys table */}
      {loading ? (
        <p className="text-sm text-slate-500">Loading...</p>
      ) : keys.length === 0 ? (
        <p className="text-sm text-slate-500">No API keys for this user.</p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-900">
                <th className="px-4 py-3 text-left font-medium text-slate-400">Label</th>
                <th className="px-4 py-3 text-left font-medium text-slate-400">Prefix</th>
                <th className="px-4 py-3 text-left font-medium text-slate-400">Status</th>
                <th className="px-4 py-3 text-left font-medium text-slate-400">Created</th>
                <th className="px-4 py-3 text-right font-medium text-slate-400">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 bg-slate-900/50">
              {keys.map((key) => (
                <tr key={key.id} className="hover:bg-slate-800/40">
                  <td className="px-4 py-3 text-slate-200">{key.label}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">{key.prefix}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        key.is_active
                          ? "bg-emerald-900/50 text-emerald-300"
                          : "bg-red-900/50 text-red-300"
                      }`}
                    >
                      {key.is_active ? "Active" : "Revoked"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {new Date(key.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {key.is_active && (
                      <button
                        onClick={() => handleRevoke(key.id)}
                        disabled={revokingId === key.id}
                        className="rounded-lg px-2.5 py-1 text-xs text-red-400 hover:bg-red-900/30 disabled:opacity-50"
                      >
                        {revokingId === key.id ? "Revoking..." : "Revoke"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create modal */}
      {showCreate && (
        <CreateKeyModal
          users={users}
          onClose={() => setShowCreate(false)}
          onCreated={handleKeyCreated}
        />
      )}
    </div>
  );
}
