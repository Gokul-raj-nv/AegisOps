import axios from 'axios';
import type {
  IncidentSummary, InvestigationResult, IncidentCreate,
  IncidentResponse, ApprovalResponse,
} from '../types';

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json', 'X-User-ID': 'sre-demo-user' },
});

export const listIncidents = (skip = 0, limit = 50): Promise<IncidentSummary[]> =>
  api.get('/incidents', { params: { skip, limit } }).then(r => r.data);

export const getIncident = (id: string): Promise<InvestigationResult> =>
  api.get(`/incidents/${id}`).then(r => r.data);

export const createIncident = (payload: IncidentCreate): Promise<IncidentResponse> =>
  api.post('/incidents', payload).then(r => r.data);

export const triggerInvestigation = (id: string): Promise<IncidentResponse> =>
  api.post(`/incidents/${id}/investigate`).then(r => r.data);

export const approveRemediation = (id: string, comment?: string): Promise<ApprovalResponse> =>
  api.post(`/incidents/${id}/approve`, { comment }).then(r => r.data);

export const rejectRemediation = (id: string, comment?: string): Promise<ApprovalResponse> =>
  api.post(`/incidents/${id}/reject`, { comment }).then(r => r.data);

export default api;
