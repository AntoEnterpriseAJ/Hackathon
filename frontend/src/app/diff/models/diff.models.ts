/**
 * TypeScript models for diff API responses.
 * These mirror the Python backend models.
 */

export interface InlineDiff {
  text: string;
  type: 'equal' | 'remove' | 'add';
}

export interface LineDiff {
  type: 'equal' | 'remove' | 'add' | 'replace';
  old_text: string | null;
  new_text: string | null;
  old_line_no: number | null;
  new_line_no: number | null;
  inline_diff?: InlineDiff[];
}

export interface SectionDiff {
  name: string;
  status: 'equal' | 'modified' | 'added' | 'removed';
  lines: LineDiff[];
}

export interface LogicChange {
  type: string; // e.g., 'HOURS_CHANGED', 'ECTS_CHANGED'
  section: string;
  description: string;
  severity: 'LOW' | 'MEDIUM' | 'HIGH';
  old_value?: string;
  new_value?: string;
}

export interface DiffSummary {
  total_sections: number;
  modified: number;
  added: number;
  removed: number;
  unchanged: number;
  logic_changes_count: number;
}

export interface DiffResponse {
  sections: SectionDiff[];
  logic_changes: LogicChange[];
  summary: DiffSummary;
}

export interface DiffNarrative {
  narrative: string;
  key_changes: string[];
  action_items: string[];
}
