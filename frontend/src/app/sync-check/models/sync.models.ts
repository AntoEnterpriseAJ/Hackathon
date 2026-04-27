/**
 * Models for cross-document validation (FD ↔ Plan de Învățământ).
 * Mirror backend/schemas/cross_validation.py and template_validation.py.
 */

export interface GuardViolation {
  code: string;
  message: string;
  field?: string | null;
  fields?: string[];
}

export interface PlanCourseMatch {
  course_name: string;
  course_code?: string | null;
  year?: number | null;
  semester?: number | null;
  credits?: number | null;
  evaluation_form?: string | null;
  match_confidence: 'exact' | 'fuzzy' | 'none';
}

export interface CrossValidationResult {
  status: 'valid' | 'invalid' | 'no_match';
  fd_course_name?: string | null;
  plan_match?: PlanCourseMatch | null;
  field_violations: GuardViolation[];
  competency_violations: GuardViolation[];
  summary: string;
  details?: Record<string, unknown>;
}

/** Shape of ExtractedDocument from /api/documents/parse. */
export interface ExtractedDocument {
  document_type: string;
  summary: string;
  fields: Array<{ key: string; value: unknown; field_type: string; confidence: string }>;
  tables: Array<{ name: string; headers: string[]; rows: string[][] }>;
  source_route: 'text_pdf' | 'scanned_pdf' | 'image' | 'fast_pdfplumber' | string;
}

/** One discipline carved out of an FD bundle by /api/documents/split-fd-bundle. */
export interface FdSliceResponse {
  index: number;
  course_name_hint: string | null;
  page_start: number;
  page_end: number;
  pdf_base64: string;
}

export interface SplitFdBundleResponse {
  total_pages: number;
  fd_count: number;
  slices: FdSliceResponse[];
}

/** UC 2.2 — Competency Mapper. Mirrors backend/schemas/competency_mapping.py. */
export interface CompetencyEntry {
  code: string;
  title: string | null;
}

export interface RecommendedCompetency {
  code: string;
  title: string | null;
  rationale: string;
  confidence: 'high' | 'medium' | 'low';
}

export interface CompetencyMapping {
  fd_course_name: string | null;
  plan_program: string | null;
  catalog: CompetencyEntry[];
  declared: CompetencyEntry[];
  unknown: CompetencyEntry[];
  plan_only: CompetencyEntry[];
  recommended: RecommendedCompetency[];
  summary: string;
}

/** UC 1.1 — Structural field validation result from /api/documents/validate. */
export interface SuggestionOption {
  code: string;
  label: string;
  patch: Record<string, unknown>;
}

export interface StructuralValidationResult {
  status: 'valid' | 'invalid';
  violations: GuardViolation[];
  suggestions: SuggestionOption[];
}

/** UC 1.2 — Numeric consistency report. */
export interface NumericIssue {
  severity: 'error' | 'warning' | 'info';
  code: string;
  message: string;
  expected?: number | null;
  actual?: number | null;
  delta?: number | null;
  fields: string[];
}

export interface NumericConsistencyReport {
  issues: NumericIssue[];
  passed: number;
  total_checks: number;
  summary: string;
}

/** UC 3.1 — Bibliography freshness report. */
export interface BibliographyEntry {
  section_index: number;
  entry_index: number;
  text: string;
  latest_year: number | null;
  urls: string[];
  age_years: number | null;
  issues: string[];
}

export interface BibliographyIssue {
  severity: 'error' | 'warning' | 'info';
  code: string;
  message: string;
  section_index: number;
  entry_index: number;
  entry_text: string;
}

export interface BibliographyReport {
  entries: BibliographyEntry[];
  issues: BibliographyIssue[];
  total_entries: number;
  fresh_entries: number;
  stale_entries: number;
  undated_entries: number;
  summary: string;
}
