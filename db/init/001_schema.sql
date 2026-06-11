CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS service_credentials (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    service text NOT NULL,
    auth_type text NOT NULL,
    label text NOT NULL DEFAULT 'default',
    data_encrypted text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT service_credentials_service_check CHECK (
        service IN ('yandex_music', 'qobuz', 'navidrome')
    ),
    CONSTRAINT service_credentials_auth_type_check CHECK (
        auth_type IN ('token', 'login_password', 'login_password_url')
    ),
    CONSTRAINT service_credentials_user_service_label_unique UNIQUE (
        user_id,
        service,
        label
    )
);

CREATE TABLE IF NOT EXISTS download_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    service text NOT NULL,
    source_type text NOT NULL,
    source_id text NOT NULL,
    status text NOT NULL DEFAULT 'queued',
    progress jsonb NOT NULL DEFAULT '{}'::jsonb,
    target text NOT NULL DEFAULT 'browser',
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT download_jobs_service_check CHECK (
        service IN ('yandex_music', 'qobuz', 'navidrome')
    ),
    CONSTRAINT download_jobs_source_type_check CHECK (
        source_type IN ('album', 'track', 'playlist')
    ),
    CONSTRAINT download_jobs_status_check CHECK (
        status IN ('queued', 'running', 'done', 'failed', 'cancelled')
    ),
    CONSTRAINT download_jobs_target_check CHECK (
        target IN ('browser', 'server_library', 'navidrome')
    )
);

CREATE INDEX IF NOT EXISTS service_credentials_user_id_idx
    ON service_credentials(user_id);

CREATE INDEX IF NOT EXISTS service_credentials_user_service_idx
    ON service_credentials(user_id, service);

CREATE INDEX IF NOT EXISTS download_jobs_user_id_idx
    ON download_jobs(user_id);

CREATE INDEX IF NOT EXISTS download_jobs_user_status_idx
    ON download_jobs(user_id, status);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS users_set_updated_at ON users;
CREATE TRIGGER users_set_updated_at
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS service_credentials_set_updated_at ON service_credentials;
CREATE TRIGGER service_credentials_set_updated_at
BEFORE UPDATE ON service_credentials
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS download_jobs_set_updated_at ON download_jobs;
CREATE TRIGGER download_jobs_set_updated_at
BEFORE UPDATE ON download_jobs
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
