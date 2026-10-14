import { useState } from 'react';
import type { ApprovalResponse, RemediationPlanResponse } from '../types';
import { approveRemediation, rejectRemediation } from '../api/client';
import { RiskBadge } from './Badges';

interface Props {
  incidentId: string;
  plan: RemediationPlanResponse;
  approval: ApprovalResponse | null;
  onDecision: () => void;
}

export default function ApprovalPanel({ incidentId, plan, approval, onDecision }: Props) {
  const [comment, setComment] = useState('');
  const [loading, setLoading] = useState<'approve' | 'reject' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const alreadyDecided = approval && approval.status !== 'PENDING';

  const handle = async (action: 'approve' | 'reject') => {
    setLoading(action);
    setError(null);
    try {
      if (action === 'approve') await approveRemediation(incidentId, comment);
      else await rejectRemediation(incidentId, comment);
      onDecision();
    } catch (e: unknown) {
      setError((e as Error).message ?? 'Action failed');
    } finally {
      setLoading(null);
    }
  };

  if (alreadyDecided && approval) {
    return (
      <div className={approval.status === 'APPROVED' ? 'approval-approved-box' : 'approval-rejected-box'}>
        <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>
          {approval.status === 'APPROVED' ? '✅' : '❌'}
        </div>
        <div style={{ fontWeight: 700, marginBottom: '0.25rem' }}>
          Remediation {approval.status === 'APPROVED' ? 'Approved' : 'Rejected'}
        </div>
        <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
          by {approval.approved_by ?? 'unknown'}
          {approval.comment && <> — "{approval.comment}"</>}
        </div>
      </div>
    );
  }

  return (
    <div className="approval-panel">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
        <div className="approval-title">⚠ Human Approval Required</div>
        <RiskBadge risk={plan.risk_level} />
      </div>
      <div className="approval-desc">
        The AI has generated a <strong>{plan.risk_level}-risk</strong> remediation plan.
        Review the steps and approve or reject before execution.
      </div>

      {error && <div className="alert alert-error">⚠ {error}</div>}

      <textarea
        className="approval-comment"
        placeholder="Add a comment (optional)..."
        value={comment}
        onChange={e => setComment(e.target.value)}
      />

      <div className="approval-actions">
        <button
          id="btn-approve-remediation"
          className="btn btn-success"
          style={{ flex: 1 }}
          disabled={loading !== null}
          onClick={() => handle('approve')}
        >
          {loading === 'approve' ? '...' : '✓ Approve'}
        </button>
        <button
          id="btn-reject-remediation"
          className="btn btn-danger"
          style={{ flex: 1 }}
          disabled={loading !== null}
          onClick={() => handle('reject')}
        >
          {loading === 'reject' ? '...' : '✕ Reject'}
        </button>
      </div>
    </div>
  );
}
