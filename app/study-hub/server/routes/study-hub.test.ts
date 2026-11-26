import { describe, expect, test } from 'vitest';
import { missingDomains, statusFromRun } from './study-hub';

describe('study package checks', () => {
  test('rejects packages without the required dm, ae and lb files', () => {
    const full = [
      'S/study_metadata.json',
      'S/edc/demographics.csv',
      'S/edc/adverse_events.csv',
      'S/vendor/central_lab_results.xlsx',
    ];
    expect(missingDomains(full)).toEqual([]);
    expect(missingDomains(['S/study_metadata.json', 'S/edc/demographics.csv'])).toEqual(['ae', 'lb']);
  });
});

describe('submission status from a job run', () => {
  const ok = (key: string, result = 'SUCCESS') => ({ task_key: key, result });

  test('is processing until the run terminates', () => {
    expect(statusFromRun('RUNNING', undefined, [])).toBe('PROCESSING');
  });

  test('is published when the run succeeds without the manual hand-off', () => {
    expect(statusFromRun('TERMINATED', 'SUCCESS', [ok('ai_data_modelling'), ok('publish_portfolio')])).toBe('PUBLISHED');
  });

  test('waits for manual modelling when the hand-off task ran', () => {
    const tasks = [ok('ai_data_modelling'), ok('manual_modelling_handoff'), ok('publish_portfolio', 'EXCLUDED')];
    expect(statusFromRun('TERMINATED', 'SUCCESS', tasks)).toBe('AWAITING_MANUAL_MODELLING');
  });

  test('a skipped hand-off task does not count', () => {
    expect(statusFromRun('TERMINATED', 'SUCCESS', [ok('manual_modelling_handoff', 'EXCLUDED')])).toBe('PUBLISHED');
  });

  test('is failed when the run does not succeed', () => {
    expect(statusFromRun('TERMINATED', 'FAILED', [])).toBe('FAILED');
  });
});
