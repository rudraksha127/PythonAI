"use client";

import { useState } from "react";
import Link from "next/link";
import { Zap, Eye, EyeOff } from "lucide-react";

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match");
      setLoading(false);
      return;
    }

    if (password.length < 6) {
      setError("Password must be at least 6 characters");
      setLoading(false);
      return;
    }

    try {
      const res = await fetch("http://localhost:7337/api/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: email, password }),
      });
      const data = await res.json();
      if (data.success) {
        setSuccess(true);
        localStorage.setItem("forgeai_token", data.token);
        localStorage.setItem("forgeai_username", data.username);
        setTimeout(() => {
          window.location.href = "/";
        }, 1500);
      } else {
        setError(data.error || "Registration failed");
      }
    } catch {
      setError("Could not connect to server. Make sure ForgeAI is running.");
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="text-center">
          <div className="w-16 h-16 rounded-full bg-success/20 flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-success" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h2 className="text-2xl font-bold text-text-primary mb-2">Account Created!</h2>
          <p className="text-text-muted">Redirecting to dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-xl bg-forge-primary/20 flex items-center justify-center">
              <Zap size={22} className="text-forge-primary" />
            </div>
            <h1 className="text-2xl font-bold text-text-primary">ForgeAI</h1>
          </div>
          <p className="text-text-muted">Create your account</p>
        </div>

        <form onSubmit={handleSubmit} className="glass rounded-xl p-6 space-y-4 border border-forge-border">
          {error && (
            <div className="bg-error/10 border border-error/30 text-error text-sm rounded-lg px-4 py-3">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">
              Email / Username
            </label>
            <input
              type="text"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-4 py-2.5 bg-forge-elevated border border-forge-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-forge-primary/50 focus:border-forge-primary transition-all"
              placeholder="you@example.com"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">
              Password
            </label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-2.5 bg-forge-elevated border border-forge-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-forge-primary/50 focus:border-forge-primary transition-all pr-10"
                placeholder="At least 6 characters"
                required
                minLength={6}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary"
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">
              Confirm Password
            </label>
            <input
              type={showPassword ? "text" : "password"}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full px-4 py-2.5 bg-forge-elevated border border-forge-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-forge-primary/50 focus:border-forge-primary transition-all"
              placeholder="Repeat your password"
              required
              minLength={6}
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 px-4 bg-forge-primary text-white font-medium rounded-lg hover:bg-forge-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {loading ? "Creating account..." : "Create Account"}
          </button>

          <p className="text-xs text-text-muted text-center">
            By signing up, you agree to the{" "}
            <a href="#" className="text-forge-primary hover:underline">Terms of Service</a>
            {" "}and{" "}
            <a href="#" className="text-forge-primary hover:underline">Privacy Policy</a>
          </p>
        </form>

        <p className="text-center mt-6 text-sm text-text-muted">
          Already have an account?{" "}
          <Link href="/login" className="text-forge-primary hover:underline font-medium">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
