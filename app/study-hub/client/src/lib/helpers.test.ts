import { describe, expect, test } from 'vitest';
import { pivot } from './pivot';
import { domainForPath } from './submissions';

describe('study hub helpers', () => {
  test('maps study package files to SDTM domains', () => {
    expect(domainForPath('ONC-101/edc/demographics.csv')).toBe('dm');
    expect(domainForPath('ONC-101/vendor/central_lab_results.xlsx')).toBe('lb');
    expect(domainForPath('study_metadata.json')).toBe('meta');
    expect(domainForPath('ONC-101/edc/unknown.csv')).toBeNull();
  });

  test('pivots long rows into wide chart rows, filling missing series with 0', () => {
    const { data, series } = pivot(
      [
        { month: '2026-01', arm: 'A', n: 2 },
        { month: '2026-01', arm: 'B', n: 3 },
        { month: '2026-02', arm: 'A', n: 5 },
      ],
      'month',
      'arm',
      'n',
    );
    expect(series).toEqual(['A', 'B']);
    expect(data).toEqual([
      { month: '2026-01', A: 2, B: 3 },
      { month: '2026-02', A: 5, B: 0 },
    ]);
  });

  test('forward-fills missing cumulative series instead of dropping to 0', () => {
    const { data } = pivot(
      [
        { month: '2026-01', arm: 'A', n: 2 },
        { month: '2026-01', arm: 'B', n: 3 },
        { month: '2026-02', arm: 'A', n: 5 },
      ],
      'month',
      'arm',
      'n',
      { fill: 'forward' },
    );
    expect(data).toEqual([
      { month: '2026-01', A: 2, B: 3 },
      { month: '2026-02', A: 5, B: 3 },
    ]);
  });
});
