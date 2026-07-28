export type MandantStatus = "aktiv" | "pausiert" | "gekuendigt";
export type Role = "super_admin" | "mandant_admin" | "disponent" | "techniker";

export interface Mandant {
  id: string;
  name: string;
  slug: string;
  branche: string | null;
  status: MandantStatus;
  branding: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface User {
  id: string;
  mandant_id: string | null;
  email: string;
  role: Role;
  name: string;
  avatar_url: string | null;
  aktiv: boolean;
  created_at: string;
  updated_at: string;
}

export interface AuditLogEntry {
  id: number;
  mandant_id: string | null;
  actor_user_id: string | null;
  aktion: string;
  entity_type: string | null;
  entity_id: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface CurrentUser {
  id: string;
  mandant_id: string | null;
  mandant_name: string | null;
  role: Role;
  name: string;
  email: string;
  impersonated_by: string | null;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface ImpersonateResponse {
  access_token: string;
  token_type: string;
  mandant_id: string;
  expires_in_minutes: number;
}
