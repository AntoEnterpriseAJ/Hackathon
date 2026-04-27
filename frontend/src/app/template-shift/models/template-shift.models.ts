export type ShiftConfidence =
  | 'exact'
  | 'fuzzy'
  | 'llm-high'
  | 'llm-medium'
  | 'llm-low'
  | 'placeholder';

export interface SectionMatchReport {
  new_heading: string;
  old_heading: string | null;
  confidence: ShiftConfidence;
  rationale?: string | null;
}

export interface AdminUpdateReport {
  field: string;
  value: string;
}

export interface ShiftReport {
  matches: SectionMatchReport[];
  admin_updates: AdminUpdateReport[];
  placeholders: string[];
  llm_used: boolean;
}

export interface ShiftResult {
  blob: Blob;
  report: ShiftReport;
  filename: string;
}
