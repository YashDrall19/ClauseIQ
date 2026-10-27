import type {
  AnalyzeResponse,
  ChatResponse,
  ContractDetail,
  ContractRecord,
  ContractSource,
  StructuredAnswer,
  UploadResponse,
} from '@/types/contract';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  if (!response.ok) {
    let message = `The backend returned an error (${response.status}).`;
    try {
      const body = await response.json() as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep the HTTP status message when the server did not return JSON.
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

type ApiSource = { page: number; excerpt: string; section_title?: string | null };
type ApiAnswer = { answer: string; confidence_score: number; found_in_contract: boolean; sources: ApiSource[] };
type ApiAnalysisItem = {
  question_id?: string;
  question: string;
  status: 'completed' | 'failed';
  answer: ApiAnswer | null;
  error?: string | null;
};

function toSource(source: ApiSource): ContractSource {
  return { page_number: source.page, excerpt: source.excerpt, section_title: source.section_title ?? undefined };
}

function toStructuredAnswer(item: ApiAnalysisItem): StructuredAnswer | null {
  if (item.status !== 'completed' || !item.answer) return null;
  return {
    question: item.question,
    answer: item.answer.answer,
    confidence_score: Math.round(item.answer.confidence_score * 100),
    found_in_contract: item.answer.found_in_contract,
    sources: item.answer.sources.map(toSource),
  };
}

export async function uploadContract(file: File, signal?: AbortSignal): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await request<{
    contract_id: string;
    filename: string;
    page_count: number | null;
    extraction_method: string;
    processing_status: string;
    analysis_status: string;
  }>('/api/contracts/upload', { method: 'POST', body: formData, signal });
  return response;
}

export async function analyzeContract(contractId: string, signal?: AbortSignal): Promise<AnalyzeResponse> {
  const response = await request<{
    contract_id: string;
    status: 'completed' | 'partial' | 'failed';
    answers: ApiAnalysisItem[];
  }>(`/api/contracts/${contractId}/analyze`, { method: 'POST', signal });
  return {
    contract_id: response.contract_id,
    status: response.status,
    answers: response.answers.flatMap((item) => {
      const answer = toStructuredAnswer(item);
      return answer ? [answer] : [];
    }),
  };
}

export async function askContract(contractId: string, question: string, signal?: AbortSignal): Promise<ChatResponse> {
  const response = await request<ApiAnswer & { contract_id: string }>(`/api/contracts/${contractId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
    signal,
  });
  return {
    question,
    answer: response.answer,
    confidence_score: Math.round(response.confidence_score * 100),
    found_in_contract: response.found_in_contract,
    sources: response.sources.map(toSource),
  };
}

export async function getContracts(signal?: AbortSignal): Promise<ContractRecord[]> {
  const response = await request<{
    items: {
      contract_id: string;
      filename: string;
      uploaded_at: string;
      processing_status: string;
      page_count: number | null;
      extraction_method: string;
      analysis_status: string;
    }[];
  }>('/api/contracts', { signal });
  return response.items.map((item) => ({
    id: item.contract_id,
    name: item.filename,
    created_at: item.uploaded_at,
    status: item.analysis_status as ContractRecord['status'],
  }));
}

export function getContract(contractId: string, signal?: AbortSignal): Promise<ContractDetail> {
  return request<ContractDetail>(`/api/contracts/${contractId}`, { signal });
}

export async function getContractAnswers(contractId: string, signal?: AbortSignal): Promise<StructuredAnswer[]> {
  const response = await getContract(contractId, signal);
  return (response.answers ?? []).flatMap((item) => {
    const answer = toStructuredAnswer(item);
    return answer ? [answer] : [];
  });
}
