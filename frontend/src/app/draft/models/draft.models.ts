import { ExtractedDocument } from '../../sync-check/models/sync.models';

export interface PlanCourseSummary {
  course_name: string;
  course_code?: string | null;
  year?: number | null;
  semester?: number | null;
  credits?: number | null;
  evaluation_form?: string | null;
  categoria_formativa?: string | null;
  total_hours?: number | null;
  weekly_hours?: string | null;
}

export interface PlanCourseListResponse {
  program?: string | null;
  courses: PlanCourseSummary[];
}

export interface FdDraftSection {
  title: string;
  body: string;
}

export interface SelectedCompetency {
  code: string;
  title: string;
  ri_bullets: string[];
  rationale?: string | null;
}

export interface FdDraft {
  course_name: string;
  course_code?: string | null;
  year?: number | null;
  semester?: number | null;
  credits?: number | null;
  evaluation_form?: string | null;
  categoria_formativa?: string | null;
  total_hours?: number | null;
  weekly_hours?: string | null;
  competencies: string[];
  selected_cp: SelectedCompetency[];
  selected_ct: SelectedCompetency[];
  picker_fallback_reason?: string | null;
  sections: FdDraftSection[];
  markdown: string;
  ai_generated: boolean;
  summary: string;
}

export type { ExtractedDocument };
