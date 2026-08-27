import { Job, STATUS_LABELS } from "@/lib/api";

const STEPS = [
  { key: "downloading", label: "Yuklanmoqda" },
  { key: "transcribing", label: "Transkripsiya" },
  { key: "translating", label: "Tarjima" },
  { key: "synthesizing", label: "TTS" },
  { key: "merging", label: "Birlashtirish" },
  { key: "completed", label: "Tayyor" },
] as const;

interface Props {
  job: Job;
}

export default function ProgressBar({ job }: Props) {
  const currentIndex = STEPS.findIndex((s) => s.key === job.status);
  const isFailed = job.status === "failed";

  return (
    <div className="w-full space-y-4">
      {/* Progress qadamlar */}
      <div className="flex items-center justify-between">
        {STEPS.map((step, i) => {
          const isDone = currentIndex > i;
          const isActive = currentIndex === i;
          return (
            <div key={step.key} className="flex flex-col items-center gap-1">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-all ${
                  isFailed && isActive
                    ? "bg-blue-500 text-white"
                    : isDone
                    ? "bg-green-500 text-white"
                    : isActive
                    ? "bg-blue-500 text-white animate-pulse"
                    : "bg-gray-200 text-gray-400"
                }`}
              >
                {isDone ? "✓" : i + 1}
              </div>
              <span
                className={`text-xs ${
                  isActive ? "text-blue-600 font-semibold" : "text-gray-400"
                }`}
              >
                {step.label}
              </span>
            </div>
          );
        })}
      </div>

      {/* Progress bar */}
      <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            isFailed ? "bg-blue-500" : "bg-blue-500"
          }`}
          style={{ width: `${job.progress}%` }}
        />
      </div>

      {/* Status matn */}
      <div className="flex justify-between items-center text-sm">
        <span className={isFailed ? "text-blue-600" : "text-gray-600"}>
          {job.status_message || STATUS_LABELS[job.status]}
        </span>
        <span className="font-semibold text-gray-700">
          {Math.round(job.progress)}%
        </span>
      </div>

      {/* Xatolik xabari */}
      {isFailed && job.error_message && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-700">
          <strong>Xatolik:</strong> {job.error_message}
        </div>
      )}
    </div>
  );
}
