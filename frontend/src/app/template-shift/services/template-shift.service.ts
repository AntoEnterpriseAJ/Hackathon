import { HttpClient, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import { ShiftReport, ShiftResult } from '../models/template-shift.models';

@Injectable({ providedIn: 'root' })
export class TemplateShiftService {
  private readonly http = inject(HttpClient);

  migrate(oldFd: File, template: File, plan: File | null): Observable<ShiftResult> {
    const form = new FormData();
    form.append('old_fd', oldFd, oldFd.name);
    form.append('new_template', template, template.name);
    if (plan) {
      form.append('plan', plan, plan.name);
    }

    return this.http
      .post('/api/documents/shift-template', form, {
        observe: 'response',
        responseType: 'blob',
      })
      .pipe(
        map((response: HttpResponse<Blob>) => {
          const headerValue = response.headers.get('X-Shift-Report') ?? '';
          const report = decodeReport(headerValue);
          return {
            blob: response.body ?? new Blob(),
            report,
            filename: 'fisa_disciplinei_migrated.docx',
          };
        }),
      );
  }
}

function decodeReport(headerValue: string): ShiftReport {
  if (!headerValue) {
    return { matches: [], admin_updates: [], placeholders: [], llm_used: false };
  }
  const binary = atob(headerValue);
  const bytes = Uint8Array.from(binary, (ch) => ch.charCodeAt(0));
  const json = new TextDecoder('utf-8').decode(bytes);
  return JSON.parse(json) as ShiftReport;
}
