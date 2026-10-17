// Response shapes of GET /api/verify/run (api/verify.py) and GET /api/evidence (api/evidence.py).

export interface VerifyCase {
  id: string;
  title_vi: string;
  /** What is tried. */
  input_vi: string;
  /** What must happen. */
  expected_vi: string;
  /** What happened on this run. */
  actual_vi: string;
  pass: boolean;
  duration_ms: number;
}

export interface VerifyRun {
  ran_at: string;
  duration_ms: number;
  passed: number;
  total: number;
  cases: VerifyCase[];
}

export type Verdict = "pass" | "fail" | "mixed" | "measured" | "not_run";

export interface EvidenceItem {
  id: string;
  /** The claim, asked as a question. */
  title_vi: string;
  data_vi: string;
  /** Repo-relative path of the experiment report. */
  report: string;
  pre_registered: boolean;
  verdict: Verdict;
  headline_vi: string;
}

export interface Evidence {
  items: EvidenceItem[];
  counts: Partial<Record<Verdict, number>>;
  note_vi: string;
}
