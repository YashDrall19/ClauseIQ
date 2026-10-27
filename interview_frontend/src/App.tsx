import { useEffect, useRef, useState } from 'react';
import { Bot, FileText, History, Loader2, Send, ShieldCheck, Sparkles, Upload } from 'lucide-react';
import { askContract, getContractAnswers, getContracts, uploadContract } from '@/services/api';
import type { ChatResponse, ContractRecord, StructuredAnswer } from '@/types/contract';

type Message = { role: 'user' | 'assistant'; text: string };
const acceptedTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain'];

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(value));
}

function confidenceStyle(score: number) {
  if (score >= 75) return 'bg-emerald-50 text-emerald-700';
  if (score >= 45) return 'bg-amber-50 text-amber-700';
  return 'bg-rose-50 text-rose-700';
}

function AnswerList({ answers }: { answers: StructuredAnswer[] }) {
  if (!answers.length) return <p className="rounded-xl border border-dashed border-slate-300 px-5 py-10 text-center text-sm text-slate-500">Upload a contract to see its key terms here.</p>;
  return <div className="space-y-3">{answers.map((item) => <article key={item.question} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="flex flex-wrap items-start justify-between gap-3"><h3 className="font-semibold text-slate-900">{item.question}</h3><span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-bold ${confidenceStyle(item.confidence_score)}`}>Confidence: {item.confidence_score}%</span></div><p className="mt-2 text-sm leading-6 text-slate-600">{item.found_in_contract ? item.answer : 'The contract does not explicitly state this information.'}</p>{item.sources[0] && <p className="mt-3 border-l-2 border-indigo-400 pl-3 text-xs leading-5 text-slate-500">Page {item.sources[0].page_number}: {item.sources[0].excerpt}</p>}</article>)}</div>;
}

export default function App() {
  const [file, setFile] = useState<File | null>(null);
  const [contractId, setContractId] = useState<string | null>(null);
  const [answers, setAnswers] = useState<StructuredAnswer[]>([]);
  const [history, setHistory] = useState<ContractRecord[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false);
  const [chatting, setChatting] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const refreshHistory = async () => {
    try { setHistory(await getContracts()); } catch { /* The upload workflow remains usable if history is unavailable. */ }
  };
  useEffect(() => { void refreshHistory(); }, []);

  const selectFile = (candidate: File | undefined) => {
    if (!candidate) return;
    const extension = candidate.name.split('.').pop()?.toLowerCase();
    if (!acceptedTypes.includes(candidate.type) && !['pdf', 'docx', 'txt'].includes(extension ?? '')) { setError('Choose a PDF, DOCX, or TXT file.'); return; }
    if (candidate.size > 20 * 1024 * 1024) { setError('The file must be 20 MB or smaller.'); return; }
    setFile(candidate); setContractId(null); setAnswers([]); setMessages([]); setError('');
  };

  const analyze = async () => {
    if (!file || busy) return;
    setBusy(true); setError('');
    try {
      const uploaded = await uploadContract(file);
      if (uploaded.analysis_status === 'failed') throw new Error('The AI provider could not analyze this contract. Please try again.');
      setContractId(uploaded.contract_id); setAnswers(await getContractAnswers(uploaded.contract_id)); await refreshHistory();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to analyze this contract.'); }
    finally { setBusy(false); }
  };

  const openHistory = async (item: ContractRecord) => {
    setError(''); setBusy(true);
    try { setContractId(item.id); setAnswers(await getContractAnswers(item.id)); setMessages([]); setFile(null); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to open this contract.'); }
    finally { setBusy(false); }
  };

  const send = async () => {
    if (!contractId || !question.trim() || chatting) return;
    const text = question.trim(); setQuestion(''); setMessages((items) => [...items, { role: 'user', text }]); setChatting(true);
    try {
      const reply: ChatResponse = await askContract(contractId, text);
      setMessages((items) => [...items, { role: 'assistant', text: reply.found_in_contract ? reply.answer : 'The contract does not explicitly state this information.' }]);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to answer that question.'); }
    finally { setChatting(false); }
  };

  return <main className="min-h-screen bg-slate-50 text-slate-800"><header className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-6xl items-center gap-3 px-5 py-4"><span className="grid h-10 w-10 place-items-center rounded-xl bg-indigo-600 text-white"><FileText size={20} /></span><div><h1 className="font-bold text-slate-950">ClauseIQ</h1><p className="text-xs text-slate-500">Contract analysis with cited source text</p></div></div></header><div className="mx-auto grid max-w-6xl gap-6 px-5 py-8 lg:grid-cols-[1fr_320px]"><section><div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><p className="text-xs font-bold uppercase tracking-widest text-indigo-600">New analysis</p><h2 className="mt-2 text-2xl font-bold text-slate-950">Understand a contract in minutes</h2><p className="mt-2 text-sm leading-6 text-slate-500">Upload a PDF, DOCX, or TXT file. Text is extracted locally before selected excerpts are sent to the configured AI provider.</p><input ref={inputRef} className="hidden" type="file" accept=".pdf,.docx,.txt" onChange={(event) => selectFile(event.target.files?.[0])} /><button onClick={() => inputRef.current?.click()} className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-slate-300 px-4 py-8 text-sm font-semibold text-slate-600 hover:border-indigo-400 hover:bg-indigo-50"><Upload size={18} />{file ? file.name : 'Choose contract file'}</button><button disabled={!file || busy} onClick={() => void analyze()} className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-bold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50">{busy ? <Loader2 className="animate-spin" size={17} /> : <Sparkles size={17} />}{busy ? 'Analyzing…' : 'Analyze contract'}</button>{error && <p role="alert" className="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}</div><section className="mt-6"><h2 className="mb-3 text-lg font-bold text-slate-950">Key contract insights</h2><AnswerList answers={answers} /></section></section><aside className="space-y-6"><section className="rounded-2xl border border-slate-200 bg-white shadow-sm"><div className="border-b border-slate-100 p-5"><div className="flex items-center gap-2"><Bot size={18} className="text-indigo-600" /><h2 className="font-bold text-slate-950">Ask about the contract</h2></div><p className="mt-1 text-xs text-slate-500">Available after analysis.</p></div><div className="min-h-40 space-y-3 p-5">{messages.map((message, index) => <p key={index} className={`rounded-xl p-3 text-sm leading-6 ${message.role === 'user' ? 'ml-6 bg-indigo-600 text-white' : 'mr-6 bg-slate-100 text-slate-700'}`}>{message.text}</p>)}{chatting && <p className="text-sm text-slate-500">Reviewing the contract…</p>}</div><div className="border-t border-slate-100 p-4"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} disabled={!contractId || chatting} placeholder={contractId ? 'Ask a follow-up question…' : 'Analyze a contract first'} className="w-full resize-none rounded-lg border border-slate-200 p-3 text-sm outline-none focus:border-indigo-500" rows={3} /><button disabled={!contractId || !question.trim() || chatting} onClick={() => void send()} className="mt-2 flex w-full items-center justify-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white disabled:opacity-40"><Send size={15} />Send</button></div></section><section className="rounded-2xl border border-slate-200 bg-white shadow-sm"><div className="flex items-center gap-2 border-b border-slate-100 p-5"><History size={18} className="text-indigo-600" /><h2 className="font-bold text-slate-950">Saved contracts</h2></div><div className="divide-y divide-slate-100">{history.length ? history.map((item) => <button key={item.id} onClick={() => void openHistory(item)} className="block w-full px-5 py-4 text-left hover:bg-slate-50"><span className="block truncate text-sm font-semibold">{item.name}</span><span className="mt-1 block text-xs text-slate-500">{formatDate(item.created_at)} · {item.status}</span></button>) : <p className="p-5 text-sm text-slate-500">No saved contracts yet.</p>}</div></section><p className="flex gap-2 text-xs leading-5 text-slate-500"><ShieldCheck size={16} className="shrink-0" />Do not upload contracts unless you are authorized to share their text with the configured AI provider.</p></aside></div></main>;
}
