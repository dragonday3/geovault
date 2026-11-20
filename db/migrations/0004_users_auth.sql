-- 0004: user accounts, refresh tokens, audit log.

-- citext: case-insensitive email uniqueness (Alice@x.com == alice@x.com).
-- Trusted extension, so the database owner (geovault_app) may create it.
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TYPE user_role AS ENUM ('user', 'admin');

CREATE TABLE users (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email          citext NOT NULL UNIQUE CHECK (length(email) BETWEEN 3 AND 254),
    -- Argon2id PHC string. Never a plaintext or reversible value.
    password_hash  text NOT NULL CHECK (password_hash LIKE '$argon2id$%' OR password_hash = '!deleted'),
    role           user_role NOT NULL DEFAULT 'user',
    display_name   text NOT NULL CHECK (length(display_name) BETWEEN 1 AND 60),
    created_at     timestamptz NOT NULL DEFAULT now(),
    last_login_at  timestamptz,
    deleted_at     timestamptz
);

-- Refresh tokens are stored ONLY as SHA-256 digests: a database leak yields no usable token.
-- family_id links every token produced by rotation from one login, so reuse of an
-- already-rotated token can revoke the whole family (stolen-token detection).
CREATE TABLE refresh_tokens (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    family_id    uuid NOT NULL,
    token_hash   bytea NOT NULL UNIQUE CHECK (octet_length(token_hash) = 32),
    created_at   timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz NOT NULL,
    revoked_at   timestamptz,
    replaced_by  uuid REFERENCES refresh_tokens (id) ON DELETE SET NULL,
    CHECK (expires_at > created_at)
);
CREATE INDEX refresh_tokens_family_idx ON refresh_tokens (family_id);
CREATE INDEX refresh_tokens_user_idx ON refresh_tokens (user_id);

-- Security audit trail. Never holds passwords, tokens, notes or private coordinates.
-- actor_id is SET NULL on account deletion: the event stays as evidence, the person is gone.
CREATE TABLE audit_log (
    id           bigserial PRIMARY KEY,
    actor_id     uuid REFERENCES users (id) ON DELETE SET NULL,
    action       text NOT NULL CHECK (action ~ '^[a-z]+(\.[a-z_]+)+$'),
    target_type  text CHECK (target_type ~ '^[a-z_]{1,30}$'),
    target_id    text CHECK (length(target_id) <= 64),
    ip           inet,
    user_agent   text CHECK (length(user_agent) <= 300),
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_log_created_idx ON audit_log (created_at);
CREATE INDEX audit_log_actor_idx ON audit_log (actor_id);
