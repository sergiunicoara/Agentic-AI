import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Play, FileCode2 } from 'lucide-react'
import { submitReview } from '../api/client'

const EXAMPLE_DIFF = `--- a/src/auth.py
+++ b/src/auth.py
@@ -0,0 +1,28 @@
+import jwt
+import hashlib
+import sqlite3
+
+SECRET_KEY = "hardcoded-secret-key-12345"
+
+def authenticate_user(username: str, password: str):
+    conn = sqlite3.connect("users.db")
+    query = f"SELECT * FROM users WHERE username='{username}'"
+    cursor = conn.execute(query)
+    user = cursor.fetchone()
+    if not user:
+        return None
+    stored_hash = user["password_hash"]
+    input_hash = hashlib.md5(password.encode()).hexdigest()
+    if stored_hash != input_hash:
+        return None
+    token = jwt.encode(
+        {"user_id": user["id"], "admin": user.get("admin", False)},
+        SECRET_KEY,
+        algorithm="HS256"
+    )
+    return token
+
+def get_user_data(user_id, query_param):
+    conn = sqlite3.connect("users.db")
+    result = conn.execute(f"SELECT * FROM users WHERE id={user_id} AND {query_param}")
+    return result.fetchall()`

export default function NewReview() {
  const navigate = useNavigate()
  const [diff, setDiff] = useState('')
  const [title, setTitle] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!diff.trim()) {
      setError('Diff is required')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const result = await submitReview(diff, title)
      navigate(`/reviews/${result.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Submission failed')
      setLoading(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-gray-100">New Review</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Paste a git diff to run the 5-layer governed review pipeline
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Title */}
        <div>
          <label className="block text-xs font-medium text-gray-400 uppercase tracking-wider mb-2">
            Title <span className="text-gray-700 normal-case tracking-normal">(optional)</span>
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Add authentication middleware"
            className="w-full bg-gray-900 border border-gray-800 rounded-lg px-4 py-2.5 text-sm text-gray-200 placeholder-gray-700 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors"
          />
        </div>

        {/* Diff */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="block text-xs font-medium text-gray-400 uppercase tracking-wider">
              Diff
            </label>
            <button
              type="button"
              onClick={() => setDiff(EXAMPLE_DIFF)}
              className="text-xs text-violet-400 hover:text-violet-300 transition-colors flex items-center gap-1"
            >
              <FileCode2 size={11} />
              Load example
            </button>
          </div>
          <textarea
            value={diff}
            onChange={(e) => setDiff(e.target.value)}
            placeholder={`--- a/src/file.py\n+++ b/src/file.py\n@@ -1,3 +1,8 @@\n+import os\n+\n+SECRET = "hardcoded"\n ...`}
            rows={20}
            className="w-full bg-gray-900 border border-gray-800 rounded-lg px-4 py-3 text-xs font-mono text-gray-300 placeholder-gray-800 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 transition-colors resize-y scrollbar-thin"
            spellCheck={false}
          />
          {diff && (
            <p className="mt-1.5 text-xs text-gray-600">
              {diff.split('\n').length} lines · {diff.length.toLocaleString()} chars
            </p>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}

        {/* Submit */}
        <div className="flex items-center justify-between pt-2">
          <p className="text-xs text-gray-600">
            Pipeline runs Layer 1–5 in sequence · results in ~30–90s
          </p>
          <button
            type="submit"
            disabled={loading || !diff.trim()}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
          >
            {loading ? (
              <>
                <span className="w-3.5 h-3.5 border border-white/30 border-t-white rounded-full animate-spin" />
                Submitting...
              </>
            ) : (
              <>
                <Play size={14} />
                Run Review
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  )
}
