import type { AuditEventResponse } from '../types';

function formatTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

const ACTOR_LABELS: Record<string, string> = {
  'triage-agent': '🔍 Triage Agent',
  'rag-agent': '📚 RAG Agent',
  'log-analysis-agent': '📋 Log Agent',
  'diagnosis-agent': '🧠 Diagnosis Agent',
  'remediation-agent': '🔧 Remediation Agent',
  'validation-agent': '🛡 Validation Agent',
  'workflow': '⚙ Workflow',
  'human': '👤 Human',
};

export default function AuditTrail({ events }: { events: AuditEventResponse[] }) {
  if (events.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-icon">📋</div>
        <div className="empty-title">No audit events yet</div>
        <div className="empty-desc">Trigger an investigation to see the AI's decision trail.</div>
      </div>
    );
  }

  return (
    <div>
      {events.map(ev => (
        <div key={ev.id} className="audit-item">
          <div className="audit-time">{formatTime(ev.created_at)}</div>
          <div className="audit-actor">{ACTOR_LABELS[ev.actor] ?? ev.actor}</div>
          <div>
            <div className="audit-summary">{ev.summary}</div>
            <div className="audit-event-type">{ev.event_type}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
