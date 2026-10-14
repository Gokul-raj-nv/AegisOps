import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getIncident, triggerInvestigation } from '../api/client';
import type { InvestigationResult, IncidentStatus } from '../types';
import { SeverityBadge, StatusBadge, RiskBadge } from '../components/Badges';
import ConfidenceMeter from '../components/ConfidenceMeter';
import AuditTrail from '../components/AuditTrail';
import ApprovalPanel from '../components/ApprovalPanel';

const AGENT_NODES = [
  { key: 'triage', label: 'Triage Agent', icon: '🔍', desc: 'Classifying incident & fetching metrics' },
  { key: 'rag_search', label: 'RAG Search', icon: '📚', desc: 'Retrieving enterprise knowledge' },
  { key: 'log_analysis', label: 'Log Analysis', icon: '📋', desc: 'Extracting error patterns from logs' },
  { key: 'diagnosis', label: 'Diagnosis Agent', icon: '🧠', desc: 'Synthesising root cause' },
  { key: 'remediation', label: 'Remediation Agent', icon: '🔧', desc: 'Building remediation plan' },
  { key: 'validation', label: 'Validation Agent', icon: '🛡', desc: 'Safety-checking the plan' },
];

function getNodeStatus(status: IncidentStatus, idx: number): 'done' | 'active' | 'running' | 'pending' {
  const doneBefore: Record<IncidentStatus, number> = {
    OPEN: -1, INVESTIGATING: 0, DIAGNOSIS_READY: 3,
    AWAITING_APPROVAL: 5, APPROVED: 5, REJECTED: 5, RESOLVED: 5, FAILED: 5,
  };
  const done = doneBefore[status] ?? -1;
  if (status === 'INVESTIGATING' && idx === 0) return 'running';
  if (idx <= done) return 'done';
  if (idx === done + 1 && status === 'INVESTIGATING') return 'running';
  return 'pending';
}

function WorkflowProgress({ status }: { status: IncidentStatus }) {
  return (
    <div className="card">
      <div className="card-header"><span className="card-title">Agent Workflow</span></div>
      <div className="card-body">
        <div className="agent-timeline">
          <div className="timeline-line" />
          {AGENT_NODES.map((node, idx) => {
            const ns = getNodeStatus(status, idx);
            const dotCls = `timeline-dot timeline-dot-${ns}`;
            const icon = ns === 'done' ? '✓' : ns === 'running' ? '⟳' : String(idx + 1);
            return (
              <div key={node.key} className="timeline-item">
                <div className={dotCls}>{icon}</div>
                <div className="timeline-node-name">{node.icon} {node.label}</div>
                <div className="timeline-node-detail">
                  {ns === 'done' ? 'Complete' : ns === 'running' ? node.desc : 'Queued'}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default function IncidentDetail() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<InvestigationResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [activeTab, setActiveTab] = useState<'diagnosis' | 'remediation' | 'audit'>('diagnosis');

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const result = await getIncident(id);
      setData(result);
      setError(null);
    } catch {
      setError('Failed to load incident data.');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
    const isActive = (s?: IncidentStatus) => s === 'OPEN' || s === 'INVESTIGATING';
    const interval = setInterval(() => {
      if (isActive(data?.incident.status)) load();
    }, 5000);
    return () => clearInterval(interval);
  }, [load, data?.incident.status]);

  const handleInvestigate = async () => {
    if (!id) return;
    setTriggering(true);
    try { await triggerInvestigation(id); load(); }
    catch (e: unknown) { setError((e as Error).message); }
    finally { setTriggering(false); }
  };

  if (loading) return (
    <div className="main"><div className="loading-state"><div className="spinner" /><p>Loading investigation…</p></div></div>
  );
  if (error || !data) return (
    <div className="main"><div className="alert alert-error">⚠ {error ?? 'Incident not found'}</div></div>
  );

  const { incident, diagnosis, remediation_plan, approval, audit_events } = data;
  const canInvestigate = incident.status === 'OPEN' || incident.status === 'FAILED';
  const awaitingApproval = incident.status === 'AWAITING_APPROVAL';

  const tabs = [
    { key: 'diagnosis', label: `🧠 Diagnosis${diagnosis ? ` (${Math.round(diagnosis.confidence * 100)}%)` : ''}` },
    { key: 'remediation', label: `🔧 Remediation${remediation_plan ? ` (${remediation_plan.risk_level})` : ''}` },
    { key: 'audit', label: `📋 Audit Trail (${audit_events.length})` },
  ] as const;

  return (
    <div className="main">
      {/* Breadcrumb */}
      <div className="breadcrumb">
        <Link to="/">Dashboard</Link>
        <span className="breadcrumb-sep">›</span>
        <span>{incident.service}</span>
        <span className="breadcrumb-sep">›</span>
        <span className="font-mono" style={{ fontSize: '0.75rem' }}>{incident.id.slice(0, 8)}…</span>
      </div>

      {/* Hero */}
      <div className="incident-hero">
        <div className="incident-hero-header">
          <div style={{ flex: 1 }}>
            <div className="incident-id">INC • {incident.id}</div>
            <div className="incident-title">{incident.service} — {incident.description}</div>
            <div className="incident-meta">
              <SeverityBadge severity={incident.severity} />
              <StatusBadge status={incident.status} />
              {incident.error_rate != null && (
                <span className="meta-item">
                  <span style={{ color: 'var(--severity-high)' }}>⚡</span>
                  Error rate: <strong>{(incident.error_rate * 100).toFixed(1)}%</strong>
                </span>
              )}
              {incident.alert_source && (
                <span className="meta-item">📡 {incident.alert_source}</span>
              )}
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.625rem', alignItems: 'flex-end' }}>
            {canInvestigate && (
              <button id="btn-investigate" className="btn btn-primary" onClick={handleInvestigate} disabled={triggering}>
                {triggering ? '⟳ Starting…' : '🚀 Investigate'}
              </button>
            )}
            {incident.status === 'INVESTIGATING' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--severity-medium)', fontSize: '0.875rem' }}>
                <div className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
                AI agents working…
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Layout */}
      <div className="detail-layout">
        {/* Left: tabs */}
        <div className="section-gap">
          {/* Tab bar */}
          <div style={{ display: 'flex', gap: '0.5rem', borderBottom: '1px solid var(--border)', paddingBottom: '0.75rem' }}>
            {tabs.map(tab => (
              <button
                key={tab.key}
                id={`tab-${tab.key}`}
                onClick={() => setActiveTab(tab.key)}
                style={{
                  background: activeTab === tab.key ? 'rgba(124,92,252,0.15)' : 'transparent',
                  border: activeTab === tab.key ? '1px solid rgba(124,92,252,0.4)' : '1px solid transparent',
                  color: activeTab === tab.key ? 'var(--brand-purple)' : 'var(--text-muted)',
                  padding: '0.5rem 1rem', borderRadius: '8px', cursor: 'pointer',
                  fontSize: '0.8125rem', fontWeight: 600, transition: 'all 0.2s',
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Diagnosis Tab */}
          {activeTab === 'diagnosis' && (
            <div className="section-gap">
              {!diagnosis ? (
                <div className="empty-state">
                  <div className="empty-icon">🧠</div>
                  <div className="empty-title">No diagnosis yet</div>
                  <div className="empty-desc">
                    {canInvestigate ? 'Click "Investigate" to start the AI analysis.' : 'Investigation is running…'}
                  </div>
                </div>
              ) : (
                <>
                  <div className="card">
                    <div className="card-header"><span className="card-title">Root Cause</span></div>
                    <div className="card-body">
                      <ConfidenceMeter confidence={diagnosis.confidence} />
                      <div className="root-cause-box" style={{ marginTop: '1.5rem' }}>
                        <div className="root-cause-label">Diagnosed Root Cause</div>
                        <div className="root-cause-text">{diagnosis.root_cause}</div>
                      </div>
                      {diagnosis.suspected_component && (
                        <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginTop: '0.75rem' }}>
                          Suspected component: <span className="font-mono" style={{ color: 'var(--brand-cyan)' }}>{diagnosis.suspected_component}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {diagnosis.reasoning && (
                    <div className="card">
                      <div className="card-header"><span className="card-title">Reasoning Chain</span></div>
                      <div className="card-body">
                        <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                          {diagnosis.reasoning}
                        </p>
                      </div>
                    </div>
                  )}

                  {diagnosis.evidence && diagnosis.evidence.length > 0 && (
                    <div className="card">
                      <div className="card-header"><span className="card-title">Evidence Citations ({diagnosis.evidence.length})</span></div>
                      <div className="card-body">
                        <div className="evidence-list">
                          {diagnosis.evidence.map((ev, i) => (
                            <div key={i} className="evidence-item">
                              <div className="evidence-source">📄 {ev}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* Remediation Tab */}
          {activeTab === 'remediation' && (
            <div className="section-gap">
              {!remediation_plan ? (
                <div className="empty-state">
                  <div className="empty-icon">🔧</div>
                  <div className="empty-title">No remediation plan yet</div>
                  <div className="empty-desc">Remediation is generated after a successful diagnosis.</div>
                </div>
              ) : (
                <>
                  <div className="card">
                    <div className="card-header">
                      <span className="card-title">Remediation Plan</span>
                      <RiskBadge risk={remediation_plan.risk_level} />
                    </div>
                    <div className="card-body">
                      <div className="remediation-steps">
                        {remediation_plan.steps.map((step, i) => (
                          <div key={i} className="remediation-step">
                            <div className="step-number">{i + 1}</div>
                            <div className="step-text">{step}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {remediation_plan.expected_impact && (
                    <div className="card">
                      <div className="card-header"><span className="card-title">Expected Impact</span></div>
                      <div className="card-body">
                        <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                          {remediation_plan.expected_impact}
                        </p>
                      </div>
                    </div>
                  )}

                  {remediation_plan.rollback_plan && (
                    <div className="card">
                      <div className="card-header">
                        <span className="card-title">Rollback Plan</span>
                        <span style={{ fontSize: '0.75rem', color: 'var(--severity-medium)' }}>⚠ If remediation fails</span>
                      </div>
                      <div className="card-body">
                        <p className="font-mono" style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                          {remediation_plan.rollback_plan}
                        </p>
                      </div>
                    </div>
                  )}

                  {awaitingApproval && (
                    <ApprovalPanel
                      incidentId={incident.id}
                      plan={remediation_plan}
                      approval={approval}
                      onDecision={load}
                    />
                  )}

                  {approval && !awaitingApproval && (
                    <div className={approval.status === 'APPROVED' ? 'approval-approved-box' : 'approval-rejected-box'}>
                      <div style={{ fontSize: '1.5rem', marginBottom: '0.25rem' }}>
                        {approval.status === 'APPROVED' ? '✅' : '❌'}
                      </div>
                      <strong>Remediation {approval.status}</strong>
                      {approval.approved_by && <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>by {approval.approved_by}</div>}
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* Audit Tab */}
          {activeTab === 'audit' && (
            <div className="card">
              <div className="card-header"><span className="card-title">Full Audit Trail</span></div>
              <div className="card-body">
                <AuditTrail events={audit_events} />
              </div>
            </div>
          )}
        </div>

        {/* Right sidebar */}
        <div className="section-gap">
          <WorkflowProgress status={incident.status} />

          {/* Metadata */}
          <div className="card">
            <div className="card-header"><span className="card-title">Incident Info</span></div>
            <div className="card-body">
              {[
                ['Service', incident.service],
                ['Severity', ''],
                ['Status', ''],
                ['Created', new Date(incident.created_at).toLocaleString()],
                ['Updated', new Date(incident.updated_at).toLocaleString()],
              ].map(([label, value]) => (
                <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0', borderBottom: '1px solid rgba(120,100,255,0.06)', fontSize: '0.8125rem' }}>
                  <span style={{ color: 'var(--text-muted)' }}>{label}</span>
                  {label === 'Severity' ? <SeverityBadge severity={incident.severity} /> :
                   label === 'Status' ? <StatusBadge status={incident.status} /> :
                   <span className={label === 'Service' ? 'font-mono' : ''} style={{ color: 'var(--text-secondary)' }}>{value}</span>}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
