export interface ContractSource {
  page_number: number;
  excerpt: string;
  section_title?: string;
}

export interface StructuredAnswer {
  question: string;
  answer: string;
  confidence_score: number;
  sources: ContractSource[];
  found_in_contract: boolean;
}

export interface ContractRecord {
  id: string;
  name: string;
  created_at: string;
  status: 'pending' | 'completed' | 'partial' | 'failed';
}

export interface UploadResponse {
  contract_id: string;
  filename: string;
  page_count: number | null;
  extraction_method: string;
  analysis_status: string;
}

export interface AnalyzeResponse {
  contract_id: string;
  status: 'completed' | 'partial' | 'failed';
  answers: StructuredAnswer[];
}

export interface ChatResponse extends Omit<StructuredAnswer, 'question'> {
  question: string;
}

export interface ContractDetail {
  contract_id: string;
  filename: string;
  uploaded_at: string;
  analysis_status: string;
  answers: {
    question: string;
    status: 'completed' | 'failed';
    answer: {
      answer: string;
      confidence_score: number;
      found_in_contract: boolean;
      sources: { page: number; excerpt: string; section_title?: string | null }[];
    } | null;
  }[] | null;
}
