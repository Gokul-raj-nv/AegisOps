import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { listIncidents, createIncident, triggerInvestigation } from '../api/client';
import type { IncidentSummary, SeverityLevel } from '../types';
import { SeverityBadge, StatusBadge } from '../components/Badges';

function timeAgo(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

const SEVERITY_COUNTS = (incidents: IncidentSummary[]) => ({
  total: incidents.length,
  open: incidents.filter(i => i.status === 'OPEN' || i.status === 'INVESTIGATING').length,
  awaiting: incidents.filter(i => i.status === 'AWAITING_APPROVAL').length,
  critical: incidents.filter(i => i.severity === 'CRITICAL').length,
});

export default function Dashboard() {
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [form, setForm] = useState({ service: '', severity: 'HIGH' as SeverityLevel, description: '', error_rate: '' });
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await listIncidents();
      setIncidents(data);
      setError(null);
    } catch {
      setError('Cannot reach the AegisOps API. Make sure the backend is running on port 8000.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t); }, [load]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const inc = await createIncident({
        service: form.service, severity: form.severity, description: form.description,
        error_rate: form.error_rate ? parseFloat(form.error_rate) : undefined,
      });
      await triggerInvestigation(inc.id);
      setShowNew(false);
      setForm({ service: '', severity: 'HIGH', description: '', error_rate: '' });
      load();
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const counts = SEVERITY_COUNTS(incidents);

  return (
    <div className="main">
      <div className="dashboard-header">
        <div>
          <h1 className="page-title">
            <span className="gradient-text">AegisOps</span> Dashboard
          </h1>
          <p className="page-subtitle">AI-native incident investigation &amp; remediation</p>
        </div>
        <button id="btn-new-incident" className="btn btn-primary" onClick={() => setShowNew(v => !v)}>
          + New Incident
        </button>
      </div>

      {/* New Incident Form */}
      {showNew && (
        <div className="card mb-6">
          <div className="card-header">
            <span className="card-title">Report Incident</span>
            <button className="btn btn-outline btn-sm" onClick={() => setShowNew(false)}>✕</button>
          </div>
          <div className="card-body">
            <form onSubmit={handleCreate} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div>
                <label style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.375rem' }}>Service *</label>
                <input
                  id="input-service" required
                  style={{ width: '100%', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border)', borderRadius: '8px', padding: '0.625rem 0.875rem', color: 'var(--text-primary)', fontSize: '0.875rem', outline: 'none' }}
                  placeholder="e.g. payment-service"
                  value={form.service} onChange={e => setForm(f => ({ ...f, service: e.target.value }))}
                />
              </div>
              <div>
                <label style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.375rem' }}>Severity *</label>
                <select
                  id="input-severity"
                  style={{ width: '100%', background: 'rgba(0,0,0,0.5)', border: '1px solid var(--border)', borderRadius: '8px', padding: '0.625rem 0.875rem', color: 'var(--text-primary)', fontSize: '0.875rem', outline: 'none' }}
                  value={form.severity} onChange={e => setForm(f => ({ ...f, severity: e.target.value as SeverityLevel }))}
                >
                  <option value="LOW">LOW</option><option value="MEDIUM">MEDIUM</option>
                  <option value="HIGH">HIGH</option><option value="CRITICAL">CRITICAL</option>
                </select>
              </div>
              <div style={{ gridColumn: '1/-1' }}>
                <label style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.375rem' }}>Description *</label>
                <textarea
                  id="input-description" required
                  style={{ width: '100%', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border)', borderRadius: '8px', padding: '0.625rem 0.875rem', color: 'var(--text-primary)', fontSize: '0.875rem', outline: 'none', minHeight: '80px', resize: 'vertical', fontFamily: 'Inter, sans-serif' }}
                  placeholder="e.g. Payment service HTTP 500 error rate at 32%, P99 latency 30s"
                  value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                />
              </div>
              <div>
                <label style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.375rem' }}>Error Rate (0–1)</label>
                <input
                  id="input-error-rate" type="number" min="0" max="1" step="0.01"
                  style={{ width: '100%', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border)', borderRadius: '8px', padding: '0.625rem 0.875rem', color: 'var(--text-primary)', fontSize: '0.875rem', outline: 'none' }}
                  placeholder="e.g. 0.32"
                  value={form.error_rate} onChange={e => setForm(f => ({ ...f, error_rate: e.target.value }))}
                />
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-end' }}>
                <button id="btn-submit-incident" type="submit" className="btn btn-primary w-full" disabled={submitting}>
                  {submitting ? 'Creating & Investigating...' : '🚀 Create & Investigate'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="stats-grid">
        {[
          { label: 'Total Incidents', value: counts.total, gradient: 'var(--brand-gradient)' },
          { label: 'Active', value: counts.open, gradient: 'linear-gradient(135deg,#f59e0b,#f97316)' },
          { label: 'Awaiting Approval', value: counts.awaiting, gradient: 'linear-gradient(135deg,#f97316,#ef4444)' },
          { label: 'Critical', value: counts.critical, gradient: 'linear-gradient(135deg,#ef4444,#dc2626)' },
        ].map(s => (
          <div key={s.label} className="stat-card">
            <div className="stat-value" style={{ background: s.gradient, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>{s.value}</div>
            <div className="stat-label">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Incidents table */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Incidents</span>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Auto-refreshes every 8s</span>
        </div>
        <div style={{ overflowX: 'auto' }}>
          {loading && <div className="loading-state"><div className="spinner" /><span>Loading incidents…</span></div>}
          {error && <div style={{ padding: '1.5rem' }}><div className="alert alert-error">⚠ {error}</div></div>}
          {!loading && !error && incidents.length === 0 && (
            <div className="empty-state">
              <div className="empty-icon">🔒</div>
              <div className="empty-title">No incidents yet</div>
              <div className="empty-desc">Click "New Incident" to start the first AI investigation.</div>
            </div>
          )}
          {!loading && incidents.length > 0 && (
            <table className="incident-table">
              <thead>
                <tr>
                  <th>Service</th><th>Severity</th><th>Status</th><th>Description</th><th>Reported</th><th></th>
                </tr>
              </thead>
              <tbody>
                {incidents.map(inc => (
                  <tr key={inc.id} className="incident-row" onClick={() => location.assign(`/incidents/${inc.id}`)}>
                    <td><span className="incident-service">{inc.service}</span></td>
                    <td><SeverityBadge severity={inc.severity} /></td>
                    <td><StatusBadge status={inc.status} /></td>
                    <td><span className="incident-desc">{inc.id}</span></td>
                    <td><span className="incident-time">{timeAgo(inc.created_at)}</span></td>
                    <td>
                      <Link to={`/incidents/${inc.id}`} className="btn btn-outline btn-sm" onClick={e => e.stopPropagation()}>
                        View →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
