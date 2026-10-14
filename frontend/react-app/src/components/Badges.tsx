import type { SeverityLevel, IncidentStatus, RiskLevel, ApprovalStatus } from '../types';

export function SeverityBadge({ severity }: { severity: SeverityLevel }) {
  const cls: Record<SeverityLevel, string> = {
    LOW: 'badge badge-low', MEDIUM: 'badge badge-medium',
    HIGH: 'badge badge-high', CRITICAL: 'badge badge-critical',
  };
  const colors: Record<SeverityLevel, string> = {
    LOW: 'var(--severity-low)', MEDIUM: 'var(--severity-medium)',
    HIGH: 'var(--severity-high)', CRITICAL: 'var(--severity-critical)',
  };
  return (
    <span className={cls[severity]}>
      <span className="badge-dot" style={{ background: colors[severity] }} />
      {severity}
    </span>
  );
}

export function StatusBadge({ status }: { status: IncidentStatus }) {
  const labels: Record<IncidentStatus, string> = {
    OPEN: 'Open', INVESTIGATING: 'Investigating', DIAGNOSIS_READY: 'Diagnosed',
    AWAITING_APPROVAL: 'Awaiting Approval', APPROVED: 'Approved',
    REJECTED: 'Rejected', RESOLVED: 'Resolved', FAILED: 'Failed',
  };
  const clsMap: Record<IncidentStatus, string> = {
    OPEN: 'open', INVESTIGATING: 'investigating', DIAGNOSIS_READY: 'approved',
    AWAITING_APPROVAL: 'awaiting', APPROVED: 'approved',
    REJECTED: 'rejected', RESOLVED: 'resolved', FAILED: 'failed',
  };
  return <span className={`badge badge-${clsMap[status]}`}>{labels[status]}</span>;
}

export function RiskBadge({ risk }: { risk: RiskLevel }) {
  const cls: Record<RiskLevel, string> = {
    LOW: 'badge badge-low', MEDIUM: 'badge badge-medium', HIGH: 'badge badge-high',
  };
  const icons: Record<RiskLevel, string> = { LOW: '✓', MEDIUM: '⚠', HIGH: '⛔' };
  return (
    <span className={cls[risk]}>
      {icons[risk]} {risk} RISK
    </span>
  );
}

export function ApprovalStatusBadge({ status }: { status: ApprovalStatus }) {
  const map: Record<ApprovalStatus, [string, string]> = {
    PENDING: ['badge badge-awaiting', 'Pending'],
    APPROVED: ['badge badge-approved', 'Approved'],
    REJECTED: ['badge badge-rejected', 'Rejected'],
    NOT_REQUIRED: ['badge badge-approved', 'Auto-approved'],
  };
  const [cls, label] = map[status];
  return <span className={cls}>{label}</span>;
}
