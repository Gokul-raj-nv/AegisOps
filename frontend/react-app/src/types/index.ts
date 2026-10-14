// AegisOps TypeScript API types — mirror backend Pydantic schemas

export type SeverityLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type IncidentStatus =
  | 'OPEN' | 'INVESTIGATING' | 'DIAGNOSIS_READY'
  | 'AWAITING_APPROVAL' | 'APPROVED' | 'REJECTED' | 'RESOLVED' | 'FAILED';
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';
export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'NOT_REQUIRED';

export interface IncidentSummary {
  id: string;
  service: string;
  severity: SeverityLevel;
  status: IncidentStatus;
  created_at: string;
}

export interface IncidentResponse {
  id: string;
  service: string;
  severity: SeverityLevel;
  description: string;
  error_rate: number | null;
  alert_source: string | null;
  status: IncidentStatus;
  created_at: string;
  updated_at: string;
}

export interface DiagnosisResponse {
  id: string;
  incident_id: string;
  root_cause: string;
  confidence: number;
  reasoning: string | null;
  evidence: string[] | null;
  citations: { source: string; score?: number }[] | null;
  suspected_component: string | null;
  created_at: string;
}

export interface RemediationPlanResponse {
  id: string;
  incident_id: string;
  steps: string[];
  risk_level: RiskLevel;
  expected_impact: string | null;
  rollback_plan: string | null;
  rationale: string | null;
  requires_approval: boolean;
  created_at: string;
}

export interface ApprovalResponse {
  id: string;
  incident_id: string;
  status: ApprovalStatus;
  approved_by: string | null;
  comment: string | null;
  decided_at: string | null;
  created_at: string;
}

export interface AuditEventResponse {
  id: string;
  incident_id: string;
  event_type: string;
  actor: string;
  summary: string;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface AgentExecutionResponse {
  id: string;
  incident_id: string;
  agent_name: string;
  status: string;
  duration_ms: number | null;
  llm_calls: number;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface InvestigationResult {
  incident: IncidentResponse;
  agent_executions: AgentExecutionResponse[];
  diagnosis: DiagnosisResponse | null;
  remediation_plan: RemediationPlanResponse | null;
  approval: ApprovalResponse | null;
  audit_events: AuditEventResponse[];
}

export interface IncidentCreate {
  service: string;
  severity: SeverityLevel;
  description: string;
  error_rate?: number;
  alert_source?: string;
}
