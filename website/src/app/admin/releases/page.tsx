"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/lib/auth-context";
import {
  getCurrentRelease,
  getAllReleases,
  publishRelease,
  deleteRelease,
  type UpdateManifest,
} from "@/lib/admin";
import {
  Package,
  Plus,
  Upload,
  Trash2,
  AlertCircle,
  Loader2,
  X,
  Check,
  FileText,
  Shield,
  Calendar,
  HardDrive,
  Hash,
  Link as LinkIcon,
  AlertTriangle,
  Rocket,
} from "lucide-react";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const EMPTY_MANIFEST: UpdateManifest = {
  version: "",
  notes: "",
  pub_date: new Date().toISOString().slice(0, 19) + "Z",
  url: "",
  sha256: "",
  size: 0,
  mandatory: false,
};

export default function AdminReleasesPage() {
  const { token } = useAuth();
  const [releases, setReleases] = useState<UpdateManifest[]>([]);
  const [current, setCurrent] = useState<UpdateManifest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  // Modal state
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<UpdateManifest>({ ...EMPTY_MANIFEST });
  const [publishing, setPublishing] = useState(false);
  const [importMode, setImportMode] = useState(false);

  const fetchReleases = useCallback(async () => {
    if (!token) return;
    try {
      setLoading(true);
      const [cur, all] = await Promise.all([
        getCurrentRelease(token),
        getAllReleases(token),
      ]);
      setCurrent(cur);
      setReleases(all);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchReleases();
  }, [fetchReleases]);

  function openNewRelease() {
    setForm({ ...EMPTY_MANIFEST });
    setImportMode(false);
    setShowForm(true);
  }

  /** Import manifest.json from build-update-package.ps1 output */
  async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const json = JSON.parse(text);
      setForm({
        version: json.version || "",
        notes: json.notes || "",
        pub_date: json.pub_date || new Date().toISOString(),
        url: json.url || "",
        sha256: json.sha256 || "",
        size: json.size || 0,
        mandatory: json.mandatory || false,
      });
      setImportMode(false);
      setSuccess("Manifest imported. Review and publish.");
      setTimeout(() => setSuccess(""), 3000);
    } catch {
      setError("Failed to parse manifest.json");
    }
    e.target.value = "";
  }

  async function handlePublish() {
    if (!token) return;
    if (!form.version || !form.url || !form.sha256) {
      setError("Version, URL, and SHA-256 are required.");
      return;
    }
    try {
      setPublishing(true);
      await publishRelease(token, form);
      setSuccess(`Release ${form.version} published successfully.`);
      setShowForm(false);
      setTimeout(() => setSuccess(""), 4000);
      await fetchReleases();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPublishing(false);
    }
  }

  async function handleDelete(version: string) {
    if (!token) return;
    if (!confirm(`Delete release ${version}? This cannot be undone.`)) return;
    try {
      await deleteRelease(token, version);
      setSuccess(`Release ${version} deleted.`);
      setTimeout(() => setSuccess(""), 3000);
      await fetchReleases();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Releases &amp; Updates</h1>
          <p className="text-sm text-dark-400">
            Manage app update manifests served to desktop clients.
          </p>
        </div>
        <button
          onClick={openNewRelease}
          className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-700"
        >
          <Plus className="h-4 w-4" />
          New Release
        </button>
      </div>

      {/* Messages */}
      {error && (
        <div className="mb-4 flex items-center gap-3 rounded-xl bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <AlertCircle className="h-5 w-5 shrink-0" />
          {error}
          <button onClick={() => setError("")} className="ml-auto">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
      {success && (
        <div className="mb-4 flex items-center gap-3 rounded-xl bg-green-500/10 px-4 py-3 text-sm text-green-400">
          <Check className="h-5 w-5 shrink-0" />
          {success}
        </div>
      )}

      {/* Current release card */}
      {loading ? (
        <div className="flex h-40 items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-brand-500" />
        </div>
      ) : (
        <>
          <div className="mb-6">
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-dark-300">
              <Rocket className="h-4 w-4" />
              Current Release (served to clients)
            </h2>
            {current ? (
              <div className="card-gradient p-5">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="mb-1 flex items-center gap-2">
                      <span className="text-xl font-bold text-brand-400">
                        v{current.version}
                      </span>
                      {current.mandatory && (
                        <span className="rounded-full bg-red-500/15 px-2 py-0.5 text-xs font-medium text-red-400">
                          Mandatory
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-dark-500">
                      Published{" "}
                      {new Date(current.pub_date).toLocaleDateString()} ·{" "}
                      {formatBytes(current.size)}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <a
                      href={current.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="rounded-lg p-2 text-dark-400 transition hover:bg-white/5 hover:text-white"
                      title="Download URL"
                    >
                      <LinkIcon className="h-4 w-4" />
                    </a>
                  </div>
                </div>
                {current.notes && (
                  <div className="mt-3 rounded-lg bg-dark-950 p-3 text-xs text-dark-400 whitespace-pre-wrap">
                    {current.notes}
                  </div>
                )}
                <div className="mt-3 font-mono text-[10px] text-dark-600 break-all">
                  SHA-256: {current.sha256}
                </div>
              </div>
            ) : (
              <div className="card-gradient flex flex-col items-center p-8 text-center">
                <Package className="mb-3 h-10 w-10 text-dark-600" />
                <p className="text-sm text-dark-500">No release published yet.</p>
                <p className="mt-1 text-xs text-dark-600">
                  Create a release to enable over-the-air updates.
                </p>
              </div>
            )}
          </div>

          {/* Release history */}
          <div>
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-dark-300">
              <FileText className="h-4 w-4" />
              Release History
            </h2>
            {releases.length === 0 ? (
              <p className="text-sm text-dark-500">No releases found.</p>
            ) : (
              <div className="overflow-hidden rounded-xl border border-white/5">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-white/5 bg-dark-900/60">
                      <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-dark-400">
                        Version
                      </th>
                      <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-dark-400">
                        Date
                      </th>
                      <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-dark-400">
                        Size
                      </th>
                      <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-dark-400">
                        Flags
                      </th>
                      <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-dark-400 text-right">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {releases.map((r) => (
                      <tr
                        key={r.version}
                        className="border-b border-white/5 transition hover:bg-white/[0.02]"
                      >
                        <td className="px-4 py-3 font-medium">
                          v{r.version}
                        </td>
                        <td className="px-4 py-3 text-dark-400">
                          {new Date(r.pub_date).toLocaleDateString()}
                        </td>
                        <td className="px-4 py-3 text-dark-400">
                          {formatBytes(r.size)}
                        </td>
                        <td className="px-4 py-3">
                          {r.mandatory ? (
                            <span className="inline-flex items-center rounded-full bg-red-500/15 px-2 py-0.5 text-xs text-red-400">
                              mandatory
                            </span>
                          ) : (
                            <span className="text-xs text-dark-500">optional</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            onClick={() => handleDelete(r.version)}
                            className="rounded-lg p-1.5 text-dark-400 transition hover:bg-red-500/10 hover:text-red-400"
                            title="Delete release"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {/* New release modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-xl max-h-[90vh] overflow-y-auto rounded-2xl border border-white/10 bg-dark-900 p-6 shadow-2xl">
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-lg font-bold">Publish New Release</h2>
              <button
                onClick={() => setShowForm(false)}
                className="rounded-lg p-1.5 text-dark-400 transition hover:bg-white/10 hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Import from file */}
            <div className="mb-5 rounded-xl border border-dashed border-white/10 p-4 text-center">
              <Upload className="mx-auto mb-2 h-6 w-6 text-dark-500" />
              <p className="mb-2 text-sm text-dark-400">
                Import from <code className="text-brand-400">manifest.json</code>{" "}
                generated by <code className="text-dark-300">build-update-package.ps1</code>
              </p>
              <label className="cursor-pointer rounded-lg bg-white/5 px-4 py-1.5 text-sm font-medium text-dark-300 transition hover:bg-white/10">
                Choose File
                <input
                  type="file"
                  accept=".json"
                  onChange={handleImportFile}
                  className="hidden"
                />
              </label>
            </div>

            <div className="text-center text-xs text-dark-600 mb-4">— or fill manually —</div>

            {/* Form fields */}
            <div className="space-y-4">
              {/* Version */}
              <div>
                <label className="mb-1 flex items-center gap-1.5 text-sm font-medium text-dark-300">
                  <Shield className="h-3.5 w-3.5" />
                  Version *
                </label>
                <input
                  type="text"
                  placeholder="0.2.0"
                  value={form.version}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, version: e.target.value }))
                  }
                  className="w-full rounded-lg border border-white/10 bg-dark-950 px-3 py-2 text-sm placeholder-dark-600 outline-none focus:border-brand-500/50"
                />
              </div>

              {/* Download URL */}
              <div>
                <label className="mb-1 flex items-center gap-1.5 text-sm font-medium text-dark-300">
                  <LinkIcon className="h-3.5 w-3.5" />
                  Download URL *
                </label>
                <input
                  type="url"
                  placeholder="https://updates.promptshield.com/releases/promptShield_0.2.0_x64-setup.nsis.exe"
                  value={form.url}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, url: e.target.value }))
                  }
                  className="w-full rounded-lg border border-white/10 bg-dark-950 px-3 py-2 text-sm placeholder-dark-600 outline-none focus:border-brand-500/50"
                />
              </div>

              {/* SHA-256 */}
              <div>
                <label className="mb-1 flex items-center gap-1.5 text-sm font-medium text-dark-300">
                  <Hash className="h-3.5 w-3.5" />
                  SHA-256 Hash *
                </label>
                <input
                  type="text"
                  placeholder="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
                  value={form.sha256}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, sha256: e.target.value }))
                  }
                  className="w-full rounded-lg border border-white/10 bg-dark-950 px-3 py-2 font-mono text-xs placeholder-dark-600 outline-none focus:border-brand-500/50"
                />
              </div>

              {/* Size + Date row */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 flex items-center gap-1.5 text-sm font-medium text-dark-300">
                    <HardDrive className="h-3.5 w-3.5" />
                    Size (bytes)
                  </label>
                  <input
                    type="number"
                    placeholder="82000000"
                    value={form.size || ""}
                    onChange={(e) =>
                      setForm((f) => ({
                        ...f,
                        size: parseInt(e.target.value) || 0,
                      }))
                    }
                    className="w-full rounded-lg border border-white/10 bg-dark-950 px-3 py-2 text-sm placeholder-dark-600 outline-none focus:border-brand-500/50"
                  />
                </div>
                <div>
                  <label className="mb-1 flex items-center gap-1.5 text-sm font-medium text-dark-300">
                    <Calendar className="h-3.5 w-3.5" />
                    Publish Date
                  </label>
                  <input
                    type="datetime-local"
                    value={form.pub_date.replace("Z", "").slice(0, 16)}
                    onChange={(e) =>
                      setForm((f) => ({
                        ...f,
                        pub_date: e.target.value + ":00Z",
                      }))
                    }
                    className="w-full rounded-lg border border-white/10 bg-dark-950 px-3 py-2 text-sm outline-none focus:border-brand-500/50"
                  />
                </div>
              </div>

              {/* Release notes */}
              <div>
                <label className="mb-1 flex items-center gap-1.5 text-sm font-medium text-dark-300">
                  <FileText className="h-3.5 w-3.5" />
                  Release Notes (Markdown)
                </label>
                <textarea
                  placeholder="### What's New&#10;- Bug fixes&#10;- Performance improvements"
                  value={form.notes}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, notes: e.target.value }))
                  }
                  rows={5}
                  className="w-full rounded-lg border border-white/10 bg-dark-950 px-3 py-2 text-sm placeholder-dark-600 outline-none focus:border-brand-500/50 resize-none"
                />
              </div>

              {/* Mandatory toggle */}
              <label className="flex cursor-pointer items-center gap-3 rounded-lg border border-white/5 bg-dark-950 px-4 py-3">
                <input
                  type="checkbox"
                  checked={form.mandatory}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, mandatory: e.target.checked }))
                  }
                  className="h-4 w-4 rounded border-dark-600 bg-dark-800 text-brand-600 focus:ring-0"
                />
                <div>
                  <div className="flex items-center gap-1.5 text-sm font-medium">
                    <AlertTriangle className="h-3.5 w-3.5 text-yellow-500" />
                    Mandatory Update
                  </div>
                  <div className="text-xs text-dark-500">
                    Users will not be able to skip this update.
                  </div>
                </div>
              </label>
            </div>

            {/* Actions */}
            <div className="mt-6 flex justify-end gap-3 border-t border-white/5 pt-4">
              <button
                onClick={() => setShowForm(false)}
                className="rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-sm transition hover:bg-white/10"
              >
                Cancel
              </button>
              <button
                onClick={handlePublish}
                disabled={publishing}
                className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white transition hover:bg-brand-700 disabled:opacity-50"
              >
                {publishing ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Rocket className="h-4 w-4" />
                )}
                Publish Release
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
