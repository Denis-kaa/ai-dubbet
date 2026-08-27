"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, Loader2, AlertTriangle, Search, Send, CheckCircle2,
} from "lucide-react";
import {
  ANALYSIS_STATUS_LABELS, askQuestion, generateQuiz, generateNotes, generateBilingual,
  searchTranscript, getTranscript, clearAnalysisId, displayLanguage, TranscriptSegment, QuizQuestion, BilingualSegment,
} from "@/lib/api";
import { useAnalysisPolling } from "@/hooks/useAnalysisPolling";
import YouTubePlayer, { YouTubePlayerHandle } from "@/components/YouTubePlayer";

type Tab = "summary" | "chapters" | "transcript" | "notes" | "quiz" | "qa";

const TABS: { key: Tab; label: string }[] = [
  { key: "summary", label: "Xulosa" },
  { key: "chapters", label: "Chapterlar" },
  { key: "transcript", label: "Transkript" },
  { key: "notes", label: "Konspekt" },
  { key: "quiz", label: "Test" },
  { key: "qa", label: "Savol-javob" },
];

function formatTs(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  const sec = s % 60;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return h > 0
    ? `${h}:${mm.toString().padStart(2, "0")}:${sec.toString().padStart(2, "0")}`
    : `${mm}:${sec.toString().padStart(2, "0")}`;
}

function extractYouTubeId(url: string): string | null {
  const m = url.match(/(?:youtu\.be\/|youtube\.com\/watch\?v=|youtube\.com\/embed\/)([\w-]{11})/);
  return m ? m[1] : null;
}

export default function VideoAnalysisPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { analysis, is404 } = useAnalysisPolling(id);
  const playerRef = useRef<YouTubePlayerHandle>(null);
  const [tab, setTab] = useState<Tab>("summary");
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [qaHistory, setQaHistory] = useState<any[]>([]);
  const [quiz, setQuiz] = useState<QuizQuestion[] | null>(null);
  const [quizLoading, setQuizLoading] = useState(false);
  const [notes, setNotes] = useState<string | null>(null);
  const [notesLoading, setNotesLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<TranscriptSegment[] | null>(null);
  const [quizAnswers, setQuizAnswers] = useState<Record<number, number>>({});
  const [transcript, setTranscript] = useState<TranscriptSegment[]>([]);
  const [transcriptView, setTranscriptView] = useState<"normal" | "bilingual">("normal");
  const [bilingual, setBilingual] = useState<BilingualSegment[] | null>(null);
  const [bilingualLoading, setBilingualLoading] = useState(false);

  useEffect(() => {
    if (is404) router.push("/");
  }, [is404, router]);

  useEffect(() => {
    if (analysis?.qa_history) setQaHistory(analysis.qa_history);
    if (analysis?.quiz) setQuiz(analysis.quiz);
    if (analysis?.notes) setNotes(analysis.notes);
  }, [analysis]);

  useEffect(() => {
    if (analysis?.status === "completed" && id) {
      getTranscript(id).then((res) => setTranscript(res.segments)).catch(() => {});
    }
  }, [analysis?.status, id]);

  const seek = (seconds: number) => playerRef.current?.seekTo(seconds);

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || !id) return;
    setAsking(true);
    try {
      const entry = await askQuestion(id, question.trim());
      setQaHistory((prev) => [...prev, entry]);
      setQuestion("");
    } catch {
      alert("Savolga javob berishda xatolik yuz berdi.");
    } finally {
      setAsking(false);
    }
  };

  const handleGenerateQuiz = async () => {
    if (!id) return;
    setQuizLoading(true);
    try {
      const res = await generateQuiz(id);
      setQuiz(res.quiz);
    } catch {
      alert("Test yaratishda xatolik yuz berdi.");
    } finally {
      setQuizLoading(false);
    }
  };

  const handleGenerateNotes = async () => {
    if (!id) return;
    setNotesLoading(true);
    try {
      const res = await generateNotes(id);
      setNotes(res.notes);
    } catch {
      alert("Konspekt yaratishda xatolik yuz berdi.");
    } finally {
      setNotesLoading(false);
    }
  };

  const handleToggleBilingual = async () => {
    if (transcriptView === "bilingual") {
      setTranscriptView("normal");
      return;
    }
    setTranscriptView("bilingual");
    if (!id || bilingual) return;
    setBilingualLoading(true);
    try {
      const res = await generateBilingual(id);
      setBilingual(res.segments);
    } catch {
      alert("Bilingual ko'rinishni yaratishda xatolik yuz berdi.");
      setTranscriptView("normal");
    } finally {
      setBilingualLoading(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id || !searchQuery.trim()) {
      setSearchResults(null);
      return;
    }
    const res = await searchTranscript(id, searchQuery.trim());
    setSearchResults(res.results);
  };

  if (!analysis) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-blue-400 animate-spin" />
      </div>
    );
  }

  const videoId = extractYouTubeId(analysis.youtube_url);
  const isDone = analysis.status === "completed";
  const isFailed = analysis.status === "failed";

  return (
    <div className="min-h-screen bg-slate-900">
      <header className="border-b border-white/10 bg-slate-900/80 backdrop-blur-xl sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center gap-4">
          <button
            onClick={() => { clearAnalysisId(); router.push("/"); }}
            className="w-10 h-10 flex items-center justify-center rounded-2xl bg-white/10 hover:bg-white/20 border border-white/10 text-white transition active:scale-95 shadow-sm"
            aria-label="Orqaga qaytish"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <Link href="/" className="flex items-center gap-2 transition duration-300 hover:scale-105">
            <img src="/logodark.webp" alt="GapirAI.uz Logo" width={120} height={32} className="h-8 w-auto object-contain" />
            <span className="text-lg font-black tracking-tight text-white">
              GapirAI<span className="text-violet-500">.uz</span>
            </span>
          </Link>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">
        {!isDone && !isFailed && (
          <div className="bg-white/5 border border-white/10 rounded-2xl p-8 text-center space-y-4">
            <Loader2 className="w-10 h-10 text-blue-400 animate-spin mx-auto" />
            <h2 className="text-lg font-bold text-white">
              {ANALYSIS_STATUS_LABELS[analysis.status]}
            </h2>
            <div className="w-full max-w-sm mx-auto h-2 rounded-full bg-white/10 overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-blue-500 to-violet-500 transition-all duration-500"
                style={{ width: `${analysis.progress}%` }}
              />
            </div>
            <p className="text-sm text-gray-400">{analysis.status_message}</p>
          </div>
        )}

        {isFailed && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-2xl p-8 text-center space-y-3">
            <AlertTriangle className="w-10 h-10 text-red-400 mx-auto" />
            <h2 className="text-lg font-bold text-white">Xatolik yuz berdi</h2>
            <p className="text-sm text-gray-400">
              {analysis.error_message || "Videoni tahlil qilishda xatolik yuz berdi. Iltimos, birozdan keyin qayta urinib ko'ring."}
            </p>
          </div>
        )}

        {isDone && (
          <>
            {videoId ? (
              <YouTubePlayer ref={playerRef} videoId={videoId} />
            ) : (
              <div className="aspect-video bg-black rounded-2xl flex items-center justify-center text-gray-500 text-sm">
                Video ko'rsatib bo'lmadi
              </div>
            )}

            <h1 className="text-xl font-bold text-white">{analysis.video_title}</h1>
            <div className="flex flex-wrap gap-2 text-[11px] font-bold text-gray-400">
              {analysis.video_language && (
                <span className="bg-white/5 border border-white/10 rounded-lg px-2.5 py-1">
                  Original: {displayLanguage(analysis.video_language)}
                </span>
              )}
              <span className="bg-white/5 border border-white/10 rounded-lg px-2.5 py-1">
                Tahlil: {displayLanguage(analysis.language)}
              </span>
            </div>

            <div className="flex gap-1 p-1 rounded-2xl bg-white/5 border border-white/10 overflow-x-auto">
              {TABS.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`px-4 py-2 rounded-xl text-xs sm:text-sm font-bold whitespace-nowrap transition-all ${
                    tab === t.key ? "bg-white/10 text-blue-400 shadow" : "text-gray-400 hover:text-gray-200"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            <div className="bg-white/5 border border-white/10 rounded-2xl p-6">
              {tab === "summary" && analysis.summary && (
                <div className="space-y-6">
                  <div>
                    <h3 className="text-xs font-bold text-blue-400 uppercase tracking-widest mb-2">Qisqa</h3>
                    <p className="text-gray-200 text-sm leading-relaxed">{analysis.summary.short}</p>
                  </div>
                  <div>
                    <h3 className="text-xs font-bold text-blue-400 uppercase tracking-widest mb-2">O'rtacha</h3>
                    <p className="text-gray-200 text-sm leading-relaxed whitespace-pre-line">{analysis.summary.medium}</p>
                  </div>
                  <div>
                    <h3 className="text-xs font-bold text-blue-400 uppercase tracking-widest mb-2">Batafsil</h3>
                    <p className="text-gray-200 text-sm leading-relaxed whitespace-pre-line">{analysis.summary.detailed}</p>
                  </div>
                  {analysis.key_points && analysis.key_points.length > 0 && (
                    <div>
                      <h3 className="text-xs font-bold text-blue-400 uppercase tracking-widest mb-3">Asosiy fikrlar</h3>
                      <div className="space-y-2">
                        {analysis.key_points.map((kp, i) => (
                          <button
                            key={i}
                            onClick={() => seek(kp.timestamp)}
                            className="w-full text-left flex gap-3 items-start bg-white/[0.03] hover:bg-white/[0.06] border border-white/5 rounded-xl p-3 transition"
                          >
                            <span className="text-[11px] font-mono text-blue-400 bg-blue-500/10 rounded px-1.5 py-0.5 mt-0.5 shrink-0">
                              {formatTs(kp.timestamp)}
                            </span>
                            <div>
                              <p className="text-sm font-bold text-white">{kp.title}</p>
                              <p className="text-xs text-gray-400 mt-0.5">{kp.description}</p>
                            </div>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {tab === "chapters" && (
                <div className="space-y-2">
                  {(analysis.chapters || []).map((c, i) => (
                    <button
                      key={i}
                      onClick={() => seek(c.start)}
                      className="w-full text-left flex justify-between items-center bg-white/[0.03] hover:bg-white/[0.06] border border-white/5 rounded-xl p-3 transition"
                    >
                      <span className="text-sm font-bold text-white">{c.title}</span>
                      <span className="text-[11px] font-mono text-blue-400">{formatTs(c.start)}</span>
                    </button>
                  ))}
                  {(!analysis.chapters || analysis.chapters.length === 0) && (
                    <p className="text-sm text-gray-500">Chapterlar topilmadi.</p>
                  )}
                </div>
              )}

              {tab === "transcript" && (
                <div className="space-y-4">
                  {analysis.video_language && analysis.video_language !== analysis.language && (
                    <div className="flex gap-1 p-1 rounded-xl bg-white/5 border border-white/10 w-fit">
                      <button
                        onClick={() => setTranscriptView("normal")}
                        className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${transcriptView === "normal" ? "bg-white/10 text-blue-400" : "text-gray-400 hover:text-gray-200"}`}
                      >
                        Oddiy
                      </button>
                      <button
                        onClick={handleToggleBilingual}
                        className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${transcriptView === "bilingual" ? "bg-white/10 text-blue-400" : "text-gray-400 hover:text-gray-200"}`}
                      >
                        Bilingual
                      </button>
                    </div>
                  )}

                  {transcriptView === "normal" ? (
                    <>
                      <form onSubmit={handleSearch} className="flex gap-2">
                        <div className="flex-1 flex items-center gap-2 bg-white/5 border border-white/10 rounded-xl px-3 py-2">
                          <Search className="w-4 h-4 text-gray-500" />
                          <input
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            placeholder="Transkript ichidan qidirish..."
                            className="flex-1 bg-transparent text-sm text-white placeholder-gray-500 focus:outline-none"
                          />
                        </div>
                        <button type="submit" className="px-4 py-2 rounded-xl bg-blue-500/20 text-blue-400 text-sm font-bold hover:bg-blue-500/30 transition">
                          Qidirish
                        </button>
                      </form>
                      <div className="space-y-1.5 max-h-[500px] overflow-y-auto">
                        {(searchResults ?? transcript).map((seg, i) => (
                          <button
                            key={i}
                            onClick={() => seek(seg.start)}
                            className="w-full text-left flex gap-3 items-start hover:bg-white/[0.04] rounded-lg p-2 transition"
                          >
                            <span className="text-[11px] font-mono text-blue-400 shrink-0 mt-0.5">{formatTs(seg.start)}</span>
                            <span className="text-sm text-gray-300">{seg.text}</span>
                          </button>
                        ))}
                        {searchResults?.length === 0 && (
                          <p className="text-sm text-gray-500">Hech narsa topilmadi.</p>
                        )}
                      </div>
                    </>
                  ) : bilingualLoading ? (
                    <div className="flex items-center gap-2 text-sm text-gray-400 py-6">
                      <Loader2 className="w-4 h-4 animate-spin" /> Bilingual ko'rinish tayyorlanmoqda...
                    </div>
                  ) : (
                    <div className="space-y-3 max-h-[500px] overflow-y-auto">
                      {(bilingual ?? []).map((seg, i) => (
                        <button
                          key={i}
                          onClick={() => seek(seg.start)}
                          className="w-full text-left flex gap-3 items-start hover:bg-white/[0.04] rounded-lg p-2.5 transition border border-white/5"
                        >
                          <span className="text-[11px] font-mono text-blue-400 shrink-0 mt-0.5">{formatTs(seg.start)}</span>
                          <div className="space-y-1">
                            <p className="text-sm text-white">{seg.original}</p>
                            <p className="text-sm text-gray-400">{seg.translated}</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {tab === "notes" && (
                <div>
                  {notes ? (
                    <div className="text-sm text-gray-200 leading-relaxed whitespace-pre-line">{notes}</div>
                  ) : (
                    <button
                      onClick={handleGenerateNotes}
                      disabled={notesLoading}
                      className="px-5 py-3 rounded-xl bg-blue-500/20 text-blue-400 text-sm font-bold hover:bg-blue-500/30 transition disabled:opacity-50"
                    >
                      {notesLoading ? "Yaratilmoqda..." : "Konspekt tuzish"}
                    </button>
                  )}
                </div>
              )}

              {tab === "quiz" && (
                <div className="space-y-5">
                  {!quiz ? (
                    <button
                      onClick={handleGenerateQuiz}
                      disabled={quizLoading}
                      className="px-5 py-3 rounded-xl bg-blue-500/20 text-blue-400 text-sm font-bold hover:bg-blue-500/30 transition disabled:opacity-50"
                    >
                      {quizLoading ? "Yaratilmoqda..." : "Test tuzish"}
                    </button>
                  ) : (
                    quiz.map((q, qi) => {
                      const chosen = quizAnswers[qi];
                      return (
                        <div key={qi} className="border border-white/10 rounded-xl p-4 space-y-2">
                          <p className="text-sm font-bold text-white">{qi + 1}. {q.question}</p>
                          <div className="space-y-1.5">
                            {q.options.map((opt, oi) => {
                              const isChosen = chosen === oi;
                              const isCorrect = oi === q.correct_answer;
                              const showResult = chosen !== undefined;
                              return (
                                <button
                                  key={oi}
                                  onClick={() => setQuizAnswers((prev) => ({ ...prev, [qi]: oi }))}
                                  disabled={showResult}
                                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition border ${
                                    showResult && isCorrect
                                      ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-300"
                                      : showResult && isChosen
                                      ? "bg-red-500/15 border-red-500/30 text-red-300"
                                      : "bg-white/[0.03] border-white/5 text-gray-300 hover:bg-white/[0.06]"
                                  }`}
                                >
                                  {opt}
                                </button>
                              );
                            })}
                          </div>
                          {chosen !== undefined && (
                            <div className="flex items-start gap-2 pt-1">
                              <button onClick={() => seek(q.timestamp)} className="text-[11px] font-mono text-blue-400 shrink-0">
                                {formatTs(q.timestamp)}
                              </button>
                              <p className="text-xs text-gray-400">{q.explanation}</p>
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              )}

              {tab === "qa" && (
                <div className="space-y-4">
                  <div className="space-y-3 max-h-[400px] overflow-y-auto">
                    {qaHistory.map((qa, i) => (
                      <div key={i} className="space-y-1.5">
                        <p className="text-sm font-bold text-white">{qa.question}</p>
                        <p className="text-sm text-gray-300">{qa.answer}</p>
                        {qa.timestamps?.length > 0 && (
                          <div className="flex gap-1.5 flex-wrap">
                            {qa.timestamps.map((ts: number, ti: number) => (
                              <button
                                key={ti}
                                onClick={() => seek(ts)}
                                className="text-[11px] font-mono text-blue-400 bg-blue-500/10 rounded px-1.5 py-0.5"
                              >
                                {formatTs(ts)}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                    {qaHistory.length === 0 && (
                      <p className="text-sm text-gray-500">Video haqida savol bering.</p>
                    )}
                  </div>
                  <form onSubmit={handleAsk} className="flex gap-2">
                    <input
                      value={question}
                      onChange={(e) => setQuestion(e.target.value)}
                      placeholder="Video haqida savol bering..."
                      className="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none"
                    />
                    <button
                      type="submit"
                      disabled={asking || !question.trim()}
                      className="w-11 h-11 flex items-center justify-center rounded-xl bg-blue-500/20 text-blue-400 hover:bg-blue-500/30 transition disabled:opacity-50"
                    >
                      {asking ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                    </button>
                  </form>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
