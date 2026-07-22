-- ============================================================
-- ForgeAI Cloud Database Schema
-- ============================================================
-- Run this SQL in the Supabase SQL Editor to set up the
-- database tables, RLS policies, and triggers for ForgeAI.
--
-- Usage:
--   1. Go to https://supabase.com/dashboard/project/_/sql/new
--   2. Paste this entire file
--   3. Run it
-- ============================================================

-- ── Extensions ──────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ── Profiles ────────────────────────────────────────────────────
-- One profile per authenticated user, created on signup.

CREATE TABLE IF NOT EXISTS public.profiles (
    id              UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email           TEXT NOT NULL,
    username        TEXT NOT NULL,
    avatar_url      TEXT,
    plan_tier       TEXT NOT NULL DEFAULT 'free',
    subscription_status TEXT NOT NULL DEFAULT 'inactive',
    stripe_customer_id    TEXT,
    stripe_subscription_id TEXT,
    current_period_end    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_profiles_email ON public.profiles(email);
CREATE INDEX IF NOT EXISTS idx_profiles_username ON public.profiles(username);
CREATE INDEX IF NOT EXISTS idx_profiles_stripe_customer ON public.profiles(stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_profiles_plan ON public.profiles(plan_tier);

-- Trigger: auto-update updated_at
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_profiles_updated_at ON public.profiles;
CREATE TRIGGER trg_profiles_updated_at
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

-- ── Projects ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.projects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    repo_path       TEXT,
    languages       TEXT[] DEFAULT '{}',
    rag_indexed_at  TIMESTAMPTZ,
    current_adapter_version INTEGER DEFAULT 0,
    training_phase  INTEGER DEFAULT 0,
    base_model      TEXT DEFAULT '',
    training_schedule TEXT DEFAULT 'weekly',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_projects_user ON public.projects(user_id);
CREATE INDEX IF NOT EXISTS idx_projects_name ON public.projects(name);

DROP TRIGGER IF EXISTS trg_projects_updated_at ON public.projects;
CREATE TRIGGER trg_projects_updated_at
    BEFORE UPDATE ON public.projects
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

-- ── Training Runs ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.training_runs (
    run_id          TEXT PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    project_id      UUID REFERENCES public.projects(id) ON DELETE SET NULL,
    status          TEXT NOT NULL DEFAULT 'queued',
    progress        REAL DEFAULT 0.0,
    loss            REAL,
    eval_loss       REAL,
    acceptance_rate_before REAL,
    acceptance_rate_after  REAL,
    acceptance_delta       REAL,
    signals_used    INTEGER DEFAULT 0,
    model_name      TEXT DEFAULT '',
    adapter_path    TEXT,
    training_mode   TEXT DEFAULT 'sdft',
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_training_runs_user ON public.training_runs(user_id);
CREATE INDEX IF NOT EXISTS idx_training_runs_status ON public.training_runs(status);
CREATE INDEX IF NOT EXISTS idx_training_runs_created ON public.training_runs(created_at DESC);

DROP TRIGGER IF EXISTS trg_training_runs_updated_at ON public.training_runs;
CREATE TRIGGER trg_training_runs_updated_at
    BEFORE UPDATE ON public.training_runs
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

-- ── Capture Signals ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.capture_signals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    project_id      TEXT,
    signal_type     TEXT NOT NULL CHECK (signal_type IN ('accept', 'reject', 'edit', 'pr_merge', 'test_pass', 'test_fail')),
    file_path       TEXT,
    language        TEXT DEFAULT '',
    framework       TEXT,
    suggestion_hash TEXT,
    edit_distance   REAL DEFAULT 0.0,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signals_user ON public.capture_signals(user_id);
CREATE INDEX IF NOT EXISTS idx_signals_type ON public.capture_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_signals_created ON public.capture_signals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_user_type ON public.capture_signals(user_id, signal_type);
CREATE INDEX IF NOT EXISTS idx_signals_user_created ON public.capture_signals(user_id, created_at DESC);

-- ── API Keys (for programmatic access) ──────────────────────────

CREATE TABLE IF NOT EXISTS public.api_keys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    key_prefix      TEXT NOT NULL,  -- First 8 chars for display
    key_hash        TEXT NOT NULL,  -- SHA-256 of full key
    scopes          TEXT[] DEFAULT '{read}',
    is_active       BOOLEAN DEFAULT TRUE,
    last_used_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_api_keys_user ON public.api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON public.api_keys(is_active);

-- ── Team Members (for Team plan collaboration) ──────────────────

CREATE TABLE IF NOT EXISTS public.team_members (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_owner_id   UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    member_id       UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    role            TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member', 'viewer')),
    invited_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    accepted_at     TIMESTAMPTZ,
    UNIQUE(team_owner_id, member_id)
);

CREATE INDEX IF NOT EXISTS idx_team_members_owner ON public.team_members(team_owner_id);
CREATE INDEX IF NOT EXISTS idx_team_members_member ON public.team_members(member_id);

-- ═══════════════════════════════════════════════════════════════
-- Row Level Security (RLS) Policies
-- ═══════════════════════════════════════════════════════════════

-- ── Profiles ────────────────────────────────────────────────────

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- Users can read their own profile
CREATE POLICY "Users can view own profile"
    ON public.profiles FOR SELECT
    USING (auth.uid() = id);

-- Users can update their own profile
CREATE POLICY "Users can update own profile"
    ON public.profiles FOR UPDATE
    USING (auth.uid() = id)
    WITH CHECK (auth.uid() = id);

-- Service role can do everything (profile created via trigger)
CREATE POLICY "Service role manages all profiles"
    ON public.profiles
    FOR ALL
    USING (auth.role() = 'service_role');

-- ── Projects ────────────────────────────────────────────────────

ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own projects"
    ON public.projects FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can create own projects"
    ON public.projects FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own projects"
    ON public.projects FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own projects"
    ON public.projects FOR DELETE
    USING (auth.uid() = user_id);

-- ── Training Runs ───────────────────────────────────────────────

ALTER TABLE public.training_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own training runs"
    ON public.training_runs FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own training runs"
    ON public.training_runs FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own training runs"
    ON public.training_runs FOR UPDATE
    USING (auth.uid() = user_id);

-- ── Capture Signals ─────────────────────────────────────────────

ALTER TABLE public.capture_signals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own signals"
    ON public.capture_signals FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own signals"
    ON public.capture_signals FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- ── API Keys ────────────────────────────────────────────────────

ALTER TABLE public.api_keys ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own API keys"
    ON public.api_keys FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can create own API keys"
    ON public.api_keys FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own API keys"
    ON public.api_keys FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own API keys"
    ON public.api_keys FOR DELETE
    USING (auth.uid() = user_id);

-- ── Team Members ────────────────────────────────────────────────

ALTER TABLE public.team_members ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Members can view own team"
    ON public.team_members FOR SELECT
    USING (auth.uid() = team_owner_id OR auth.uid() = member_id);

CREATE POLICY "Owners can manage team"
    ON public.team_members FOR ALL
    USING (auth.uid() = team_owner_id);

-- ═══════════════════════════════════════════════════════════════
-- Triggers & Functions
-- ═══════════════════════════════════════════════════════════════

-- Auto-create profile on user signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, username, plan_tier, subscription_status)
    VALUES (
        NEW.id,
        COALESCE(NEW.email, ''),
        COALESCE(NEW.raw_user_meta_data ->> 'username', split_part(NEW.email, '@', 1)),
        'free',
        'inactive'
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger after auth.users insert
DROP TRIGGER IF EXISTS trg_on_auth_user_created ON auth.users;
CREATE TRIGGER trg_on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();

-- ═══════════════════════════════════════════════════════════════
-- Realtime Publication
-- ═══════════════════════════════════════════════════════════════

-- Enable Realtime for tables that need live updates
ALTER PUBLICATION supabase_realtime ADD TABLE public.training_runs;
ALTER PUBLICATION supabase_realtime ADD TABLE public.capture_signals;
