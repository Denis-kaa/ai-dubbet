import { useState, useEffect, useRef } from "react";
import { getJob, Job, JobStatus, parseApiError } from "@/lib/api";
import { getCurrentStep } from "@/components/StepProgress";
import { trackOnce } from "@/lib/analytics";

const TERMINAL_STATUSES: JobStatus[] = ["completed", "failed"];
const POLL_INTERVAL = 2000; // 2 soniya

// Stage index -> shu bosqich TUGAGANDA yuboriladigan event (StepProgress.tsx:
// 0=video, 1=transcription, 2=translation, 3=voice, 4=rendering -- rendering
// tugashi "video_completed" bilan bir xil, alohida eventi yo'q).
const STAGE_COMPLETE_EVENT: Record<number, string> = {
  1: "transcription_completed",
  2: "translation_completed",
  3: "voice_completed",
};

export function useJobPolling(jobId: string | null) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [is404, setIs404] = useState<boolean>(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevStatusRef = useRef<JobStatus | null>(null);

  useEffect(() => {
    setIs404(false);
    setJob(null);
    setError(null);
    prevStatusRef.current = null;

    if (!jobId) return;

    const poll = async () => {
      try {
        const data = await getJob(jobId);
        setJob(data);
        setError(null);

        const prevStatus = prevStatusRef.current;
        if (prevStatus !== data.status) {
          if ((prevStatus === null || prevStatus === "awaiting_payment") && data.status !== "awaiting_payment") {
            trackOnce(jobId, "processing_started");
          }
          const prevStage = prevStatus ? getCurrentStep(prevStatus) : -1;
          const currentStage = getCurrentStep(data.status);
          if (prevStage >= 0 && currentStage > prevStage) {
            for (let s = prevStage; s < currentStage; s++) {
              const evt = STAGE_COMPLETE_EVENT[s];
              if (evt) trackOnce(jobId, evt);
            }
          }
          if (data.status === "completed") trackOnce(jobId, "video_completed");
          if (data.status === "failed") trackOnce(jobId, "video_failed");
          prevStatusRef.current = data.status;
        }

        if (!TERMINAL_STATUSES.includes(data.status)) {
          timerRef.current = setTimeout(poll, POLL_INTERVAL);
        }
      } catch (err: any) {
        if (err?.response?.status === 404) {
          setIs404(true);
          setError("Job topilmadi.");
          return;
        }
        // Tarmoq uzilishi va server xatosi (500) avval bir xil umumiy
        // xabar olardi -- endi qaysi turi ekani aniq ko'rsatiladi.
        const info = parseApiError(err);
        setError(info.message);
        timerRef.current = setTimeout(poll, POLL_INTERVAL * 2);
      }
    };

    poll();

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [jobId]);

  return { job, error, is404 };
}

