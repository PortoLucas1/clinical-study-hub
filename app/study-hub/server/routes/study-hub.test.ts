import { describe, expect, test } from 'vitest';
import { missingDomains } from './study-hub';

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
