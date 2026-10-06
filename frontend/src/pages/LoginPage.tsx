import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '../api/client';
import { useAuth } from '../state/AuthContext';
import { useToast } from '../state/ToastContext';

interface LocationState {
  from?: string;
}

export function LoginPage() {
  const { user, ready, login } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  const from = (location.state as LocationState | null)?.from ?? '/';

  if (ready && user) {
    return <Navigate to={from} replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setFieldErrors({});
    try {
      const signedIn = await login(email.trim(), password);
      toast.success(`Welcome back, ${signedIn.fullName || signedIn.email}`);
      navigate(from, { replace: true });
    } catch (error) {
      if (error instanceof ApiError) {
        setFieldErrors(error.fields ?? {});
        toast.error(error.message, error.status === 401 ? 'Check your email and password.' : undefined);
      } else {
        toast.error('Sign in failed', error instanceof Error ? error.message : undefined);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="brand brand-center">
          <span className="brand-mark" aria-hidden="true">
            ✓
          </span>
          <span className="brand-text">RegTrack</span>
        </div>
        <p className="login-subtitle">Regulatory update tracking &amp; compliance dashboard</p>

        <form onSubmit={handleSubmit} noValidate>
          <label className="field">
            <span className="field-label">Email</span>
            <input
              type="email"
              name="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="admin@regtrack.local"
              aria-invalid={Boolean(fieldErrors.email)}
            />
            {fieldErrors.email ? <span className="field-error">{fieldErrors.email}</span> : null}
          </label>

          <label className="field">
            <span className="field-label">Password</span>
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••"
              aria-invalid={Boolean(fieldErrors.password)}
            />
            {fieldErrors.password ? (
              <span className="field-error">{fieldErrors.password}</span>
            ) : null}
          </label>

          <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="login-hint">
          Seeded admin: <code>admin@regtrack.local</code> / <code>Admin@12345</code>
        </p>
      </div>
    </div>
  );
}
