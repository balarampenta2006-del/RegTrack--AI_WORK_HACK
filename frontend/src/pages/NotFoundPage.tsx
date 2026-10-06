import { Link } from 'react-router-dom';

export function NotFoundPage() {
  return (
    <div className="page page-centered">
      <div className="empty-state">
        <p className="empty-title">404 — page not found</p>
        <p className="empty-hint">That route does not exist in the RegTrack dashboard.</p>
        <Link className="btn btn-primary" to="/">
          Back to dashboard
        </Link>
      </div>
    </div>
  );
}
